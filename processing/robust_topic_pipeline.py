from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable

import yake
from textblob import TextBlob

try:
    import regex as unicode_regex
except Exception:  # pragma: no cover
    unicode_regex = None

try:
    from langdetect import DetectorFactory, detect_langs

    DetectorFactory.seed = 0
except Exception:  # pragma: no cover
    detect_langs = None

try:
    from lingua import LanguageDetectorBuilder
except Exception:  # pragma: no cover
    LanguageDetectorBuilder = None

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover
    GoogleTranslator = None

try:
    from keybert import KeyBERT
except Exception:  # pragma: no cover
    KeyBERT = None

try:
    import spacy
except Exception:  # pragma: no cover
    spacy = None

try:
    from bertopic import BERTopic
    from sklearn.feature_extraction.text import CountVectorizer
except Exception:  # pragma: no cover
    BERTopic = None
    CountVectorizer = None

DEFAULT_SOURCE_RELIABILITY = {
    "news": 1.0,
    "gdelt": 0.92,
    "health": 0.96,
    "who": 0.96,
    "wiki": 0.8,
    "reddit": 0.65,
    "trends": 0.78,
    "weather": 0.75,
    "earthquakes": 0.95,
}

DEFAULT_TOPIC_CONTROLS = {
    "allowlist": [],
    "blocklist": [],
    "manual_merges": {},
    "entity_aliases": {},
}


@dataclass
class TopicIntelligenceResult:
    top_topics: list[str]
    topic_pressure: list[dict[str, Any]]
    observability: dict[str, Any]


class RobustTopicPipeline:
    """
    End-to-end robust NLP pipeline:
    - Unicode normalization
    - Language detection with confidence
    - Translation to English with cache
    - Keyphrase + entity extraction
    - Multilingual BERTopic clustering
    - Noise filtering + human controls
    - Topic pressure scoring + observability
    """

    def __init__(
        self,
        db=None,
        controls_path: str = "processing/config/topic_controls.json",
        observability_collection: str = "nlp_topic_observability",
        translation_cache_collection: str = "nlp_translation_cache",
        log_fn: Callable[[str], None] | None = None,
    ):
        self.db = db
        self.log_fn = log_fn
        self.controls_path = controls_path
        self.controls = self._load_controls(controls_path)

        self._cache_lock = Lock()
        self._translator_lock = Lock()
        self._translation_cache_mem: dict[str, dict[str, Any]] = {}

        self._spacy_nlp = None
        self._keybert_model = None
        self._lingua_detector = None

        self._yake_extractor = yake.KeywordExtractor(top=8, stopwords=None)

        if unicode_regex is not None:
            self._token_pattern = unicode_regex.compile(r"\p{L}[\p{L}\p{Mn}\p{Pd}'']{2,}")
            self._entity_pattern = unicode_regex.compile(r"\b\p{Lu}[\p{L}\p{Mn}\p{Pd}&.]+(?:\s+\p{Lu}[\p{L}\p{Mn}\p{Pd}&.]+){0,3}\b")
        else:
            self._token_pattern = re.compile(r"[A-Za-z][A-Za-z\-'']{2,}")
            self._entity_pattern = re.compile(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3}\b")

        self._observability_collection = None
        self._translation_cache_collection = None
        if self.db is not None:
            try:
                self._observability_collection = self.db[observability_collection]
                self._translation_cache_collection = self.db[translation_cache_collection]
                self._translation_cache_collection.create_index("cache_key", unique=True)
                self._translation_cache_collection.create_index("updated_at")
                self._observability_collection.create_index("timestamp")
            except Exception as exc:
                self._log(f"NLP observability setup warning: {exc}")

    def enrich_record(self, record: dict[str, Any], collection_hint: str | None = None) -> dict[str, Any]:
        """
        Enrich a streaming record with multilingual NLP metadata and dual text fields.
        """
        if not isinstance(record, dict):
            return record

        text_original = self._extract_record_text(record)
        if not text_original:
            return record

        normalized_original = self.normalize_text(text_original)
        lang, lang_conf = self.detect_language(normalized_original)
        text_en, provider, translation_conf, translated = self.translate_to_english(
            normalized_original, lang, lang_conf
        )
        text_en = self.normalize_text(text_en)

        keyphrases = self.extract_keyphrases(text_en)
        entities = self.extract_entities(text_en)
        token_terms = self.extract_token_terms(text_en)

        merged_candidates = self._apply_controls(keyphrases + entities + token_terms)
        sentiment_impact = self._sentiment_impact(text_en)

        nlp_payload = {
            "text_original": normalized_original,
            "text_en": text_en,
            "lang": lang,
            "lang_conf": round(lang_conf, 4),
            "translation_provider": provider,
            "translation_conf": round(translation_conf, 4),
            "translated": bool(translated),
            "keyphrases": keyphrases,
            "entities": entities,
            "topic_candidates": merged_candidates[:30],
            "sentiment_impact": round(sentiment_impact, 4),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "collection_hint": collection_hint,
        }

        record["text_original"] = nlp_payload["text_original"]
        record["text_en"] = nlp_payload["text_en"]
        record["lang"] = nlp_payload["lang"]
        record["lang_conf"] = nlp_payload["lang_conf"]
        record["translation_provider"] = nlp_payload["translation_provider"]
        record["translation_conf"] = nlp_payload["translation_conf"]
        record["topic_modeling_status"] = "ready" if merged_candidates else "pending"

        data_node = self._ensure_data_node(record)
        data_node["nlp_text"] = {
            "text_original": nlp_payload["text_original"],
            "text_en": nlp_payload["text_en"],
            "lang": nlp_payload["lang"],
            "lang_conf": nlp_payload["lang_conf"],
            "translation_provider": nlp_payload["translation_provider"],
            "translation_conf": nlp_payload["translation_conf"],
        }
        data_node["keyphrases"] = keyphrases
        data_node["entities"] = entities
        data_node["topic_candidates"] = merged_candidates[:30]

        return record

    def extract_topic_intelligence_from_mongo(
        self,
        db,
        top_n: int = 5,
        max_docs: int = 240,
    ) -> TopicIntelligenceResult:
        docs = self._load_documents_for_topics(db, max_docs=max_docs)
        return self.extract_topic_intelligence(docs, top_n=top_n)

    def extract_topic_intelligence(
        self,
        documents: list[dict[str, Any]],
        top_n: int = 5,
    ) -> TopicIntelligenceResult:
        now = datetime.now(timezone.utc)
        observability = self._new_observability_snapshot()

        analyzed_docs = []
        for doc in documents:
            text_original = self.normalize_text(str(doc.get("text") or ""))
            if not text_original:
                continue

            lang, lang_conf = self.detect_language(text_original)
            text_en, provider, translation_conf, translated = self.translate_to_english(text_original, lang, lang_conf)
            text_en = self.normalize_text(text_en)

            keyphrases = self.extract_keyphrases(text_en)
            entities = self.extract_entities(text_en)
            token_terms = self.extract_token_terms(text_en)
            candidates = self._apply_controls(keyphrases + entities + token_terms)

            if not candidates:
                continue

            source = str(doc.get("source") or "news").strip().lower() or "news"
            ts = self._coerce_datetime(doc.get("timestamp")) or now
            sentiment_impact = abs(float(doc.get("sentiment", self._sentiment_impact(text_en))))
            recent = (now - ts) <= timedelta(hours=6)

            observability["docs_processed"] += 1
            observability["language_mix"][lang] += 1
            observability["candidate_terms_total"] += len(candidates)
            observability["keyphrase_terms_total"] += len(keyphrases)
            observability["entity_terms_total"] += len(entities)

            if provider == "cache":
                observability["translation_cache_hit"] += 1
            elif translated:
                observability["translation_success"] += 1
            elif provider.startswith("translation_failed"):
                observability["translation_failed"] += 1
            else:
                observability["translation_skipped"] += 1

            analyzed_docs.append(
                {
                    "source": source,
                    "timestamp": ts,
                    "text_en": text_en,
                    "topic_candidates": candidates,
                    "sentiment_impact": max(0.0, min(1.0, sentiment_impact)),
                    "recent": recent,
                }
            )

        self._apply_bertopic_clusters(analyzed_docs, observability)
        topic_stats = defaultdict(lambda: {
            "count": 0,
            "recent_hits": 0,
            "source_weight_sum": 0.0,
            "sentiment_sum": 0.0,
        })

        for doc in analyzed_docs:
            unique_topics = set(doc["topic_candidates"])
            source_weight = float(DEFAULT_SOURCE_RELIABILITY.get(doc["source"], 0.75))
            for topic in unique_topics:
                stat = topic_stats[topic]
                stat["count"] += 1
                stat["recent_hits"] += 1 if doc["recent"] else 0
                stat["source_weight_sum"] += source_weight
                stat["sentiment_sum"] += float(doc["sentiment_impact"])

        if not topic_stats:
            observability["top_topics_generated"] = 0
            obs_doc = self._finalize_observability(observability)
            self._persist_observability(obs_doc)
            return TopicIntelligenceResult(top_topics=["no data"], topic_pressure=[], observability=obs_doc)

        max_count = max(float(v["count"]) for v in topic_stats.values()) or 1.0
        max_recent_hits = max(float(v["recent_hits"]) for v in topic_stats.values()) or 1.0

        scored_topics = []
        for topic, stat in topic_stats.items():
            count = int(stat["count"])
            if count <= 1 and topic not in self.controls["allowlist"]:
                observability["filtered_low_freq"] += 1
                continue

            if self._is_noisy_term(topic) and topic not in self.controls["allowlist"]:
                observability["filtered_noisy"] += 1
                continue

            frequency_component = min(1.0, count / max_count)
            burst_component = min(1.0, float(stat["recent_hits"]) / max_recent_hits)
            reliability_component = min(1.0, float(stat["source_weight_sum"]) / max(1.0, count))
            sentiment_component = min(1.0, float(stat["sentiment_sum"]) / max(1.0, count))

            pressure = (
                0.45 * frequency_component
                + 0.25 * burst_component
                + 0.20 * reliability_component
                + 0.10 * sentiment_component
            )

            scored_topics.append(
                {
                    "topic": topic,
                    "score": round(pressure * 100.0, 3),
                    "frequency": count,
                    "recency_burst": round(burst_component, 4),
                    "source_reliability": round(reliability_component, 4),
                    "sentiment_impact": round(sentiment_component, 4),
                }
            )

        scored_topics.sort(key=lambda row: (row["score"], row["frequency"]), reverse=True)
        topic_pressure = scored_topics[: max(1, top_n)]
        top_topics = [row["topic"] for row in topic_pressure]

        observability["top_topics_generated"] = len(top_topics)
        obs_doc = self._finalize_observability(observability)
        self._persist_observability(obs_doc)
        return TopicIntelligenceResult(top_topics=top_topics or ["no data"], topic_pressure=topic_pressure, observability=obs_doc)

    @staticmethod
    def normalize_text(text: str) -> str:
        if text is None:
            return ""
        normalized = unicodedata.normalize("NFKC", str(text))
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) not in {"Cc", "Cf", "Cs"})
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def detect_language(self, text: str) -> tuple[str, float]:
        sample = (text or "").strip()
        if not sample:
            return "unknown", 0.0

        lingua_lang, lingua_conf = self._detect_language_with_lingua(sample)
        if lingua_lang != "unknown" and lingua_conf > 0.0:
            return lingua_lang, lingua_conf

        if detect_langs is not None:
            try:
                guesses = detect_langs(sample[:5000])
                if guesses:
                    top = guesses[0]
                    return str(top.lang), float(top.prob)
            except Exception:
                pass

        ascii_letters = sum(1 for ch in sample if "a" <= ch.lower() <= "z")
        alpha_chars = sum(1 for ch in sample if ch.isalpha())
        ratio = (ascii_letters / alpha_chars) if alpha_chars else 0.0
        if ratio >= 0.8:
            return "en", 0.55
        return "unknown", 0.35

    def _detect_language_with_lingua(self, text: str) -> tuple[str, float]:
        if LanguageDetectorBuilder is None:
            return "unknown", 0.0

        detector = self._lingua_detector
        if detector is None:
            try:
                detector = LanguageDetectorBuilder.from_all_languages().build()
                self._lingua_detector = detector
            except Exception:
                self._lingua_detector = None
                return "unknown", 0.0

        sample = text[:5000]
        try:
            confidence_values = detector.compute_language_confidence_values(sample) or []
            if confidence_values:
                top = confidence_values[0]
                lang_name = str(getattr(top, "language", "")).split(".")[-1]
                lang = self._map_language_name_to_code(lang_name)
                conf = float(getattr(top, "value", 0.0))
                if lang != "unknown":
                    return lang, max(0.0, min(1.0, conf))

            detected = detector.detect_language_of(sample)
            if detected is not None:
                lang = self._map_language_name_to_code(str(detected).split(".")[-1])
                if lang != "unknown":
                    return lang, 0.7
        except Exception:
            return "unknown", 0.0

        return "unknown", 0.0

    @staticmethod
    def _map_language_name_to_code(language_name: str) -> str:
        if not language_name:
            return "unknown"
        key = str(language_name).strip().upper()
        mapping = {
            "ARABIC": "ar",
            "BENGALI": "bn",
            "CHINESE": "zh",
            "CZECH": "cs",
            "DANISH": "da",
            "DUTCH": "nl",
            "ENGLISH": "en",
            "FINNISH": "fi",
            "FRENCH": "fr",
            "GERMAN": "de",
            "GREEK": "el",
            "HINDI": "hi",
            "HUNGARIAN": "hu",
            "INDONESIAN": "id",
            "ITALIAN": "it",
            "JAPANESE": "ja",
            "KOREAN": "ko",
            "MALAY": "ms",
            "NORWEGIAN": "no",
            "PERSIAN": "fa",
            "POLISH": "pl",
            "PORTUGUESE": "pt",
            "PUNJABI": "pa",
            "ROMANIAN": "ro",
            "RUSSIAN": "ru",
            "SPANISH": "es",
            "SWEDISH": "sv",
            "TAMIL": "ta",
            "TELUGU": "te",
            "THAI": "th",
            "TURKISH": "tr",
            "UKRAINIAN": "uk",
            "URDU": "ur",
            "VIETNAMESE": "vi",
        }
        if key in mapping:
            return mapping[key]
        if len(key) >= 2:
            return key[:2].lower()
        return "unknown"

    def translate_to_english(self, text: str, lang: str, lang_conf: float) -> tuple[str, str, float, bool]:
        normalized = self.normalize_text(text)
        if not normalized:
            return "", "none", 0.0, False

        if lang == "en" or lang_conf < 0.55:
            return normalized, "identity", max(lang_conf, 0.5), False

        cache_key = self._translation_cache_key(normalized, lang)
        cached = self._translation_cache_get(cache_key)
        if cached:
            return str(cached.get("text_en", normalized)), "cache", float(cached.get("translation_conf", 0.95)), True

        if GoogleTranslator is None:
            return normalized, "translation_failed:no_provider", 0.0, False

        try:
            with self._translator_lock:
                translated = GoogleTranslator(source="auto", target="en").translate(normalized)
            translated_norm = self.normalize_text(translated)
            if translated_norm:
                payload = {
                    "cache_key": cache_key,
                    "lang": lang,
                    "text_en": translated_norm,
                    "translation_conf": max(0.6, min(0.99, lang_conf)),
                    "updated_at": datetime.now(timezone.utc),
                }
                self._translation_cache_set(cache_key, payload)
                return translated_norm, "deep_translator_google", float(payload["translation_conf"]), True
        except Exception as exc:
            self._log(f"Translation warning ({lang}): {exc}")
            return normalized, "translation_failed:runtime", 0.0, False

        return normalized, "translation_failed:empty", 0.0, False

    def extract_token_terms(self, text_en: str, top_n: int = 8) -> list[str]:
        tokens = [self.normalize_topic_label(tok) for tok in self._token_pattern.findall(text_en)]
        tokens = [tok for tok in tokens if tok and not self._is_noisy_term(tok)]
        if not tokens:
            return []

        counts = Counter(tokens)
        ranked = [term for term, _ in counts.most_common(max(5, top_n * 2))]

        bigrams = []
        for idx in range(len(tokens) - 1):
            left, right = tokens[idx], tokens[idx + 1]
            if left == right:
                continue
            phrase = f"{left} {right}".strip()
            if self._is_noisy_term(phrase):
                continue
            bigrams.append(phrase)

        bigram_counts = Counter(bigrams)
        ranked.extend([term for term, freq in bigram_counts.items() if freq >= 2][:top_n])
        return self._dedupe_preserve_order(ranked)[:top_n]

    def extract_keyphrases(self, text_en: str, top_n: int = 8) -> list[str]:
        if not text_en:
            return []

        candidates = []

        try:
            for phrase, _score in self._yake_extractor.extract_keywords(text_en):
                normalized = self.normalize_topic_label(phrase)
                if normalized:
                    candidates.append(normalized)
        except Exception as exc:
            self._log(f"YAKE extraction warning: {exc}")

        keybert = self._load_keybert_model()
        if keybert is not None:
            try:
                kb_keywords = keybert.extract_keywords(
                    text_en,
                    keyphrase_ngram_range=(1, 3),
                    stop_words="english",
                    top_n=top_n,
                )
                for phrase, _score in kb_keywords:
                    normalized = self.normalize_topic_label(phrase)
                    if normalized:
                        candidates.append(normalized)
            except Exception as exc:
                self._log(f"KeyBERT extraction warning: {exc}")

        if not candidates:
            candidates = self.extract_token_terms(text_en, top_n=top_n)

        cleaned = [cand for cand in self._dedupe_preserve_order(candidates) if not self._is_noisy_term(cand)]
        return cleaned[:top_n]
    def extract_entities(self, text_en: str, top_n: int = 8) -> list[str]:
        entities = []

        nlp = self._load_spacy_model()
        if nlp is not None:
            try:
                doc = nlp(text_en)
                for ent in doc.ents:
                    if ent.label_ not in {"ORG", "GPE", "PERSON", "EVENT", "NORP", "LOC"}:
                        continue
                    normalized = self.normalize_topic_label(ent.text)
                    if normalized:
                        entities.append(self._normalize_entity_alias(normalized))
            except Exception as exc:
                self._log(f"spaCy entity warning: {exc}")

        if not entities:
            for match in self._entity_pattern.findall(text_en):
                normalized = self.normalize_topic_label(match)
                if normalized:
                    entities.append(self._normalize_entity_alias(normalized))

        entities = [ent for ent in self._dedupe_preserve_order(entities) if not self._is_noisy_term(ent)]
        return entities[:top_n]

    def _apply_bertopic_clusters(self, analyzed_docs: list[dict[str, Any]], observability: dict[str, Any]) -> None:
        if BERTopic is None or CountVectorizer is None or len(analyzed_docs) < 8:
            return

        texts = [doc["text_en"] for doc in analyzed_docs if doc.get("text_en")]
        if len(texts) < 8:
            return

        observability["clustering_runs"] += 1

        try:
            vectorizer = CountVectorizer(stop_words="english")
            model = BERTopic(language="multilingual", vectorizer_model=vectorizer, calculate_probabilities=False, verbose=False)
            topics, _ = model.fit_transform(texts)

            for idx, topic_id in enumerate(topics):
                if topic_id == -1:
                    continue
                words = model.get_topic(topic_id) or []
                label_tokens = [self.normalize_topic_label(word) for word, _ in words[:3]]
                label_tokens = [token for token in label_tokens if token and not self._is_noisy_term(token)]
                if not label_tokens:
                    continue

                merged = self._apply_controls([" ".join(label_tokens)])
                if merged:
                    analyzed_docs[idx]["topic_candidates"].append(merged[0])
        except Exception as exc:
            observability["clustering_failures"] += 1
            self._log(f"BERTopic clustering warning: {exc}")

    def normalize_topic_label(self, value: str) -> str:
        label = self.normalize_text(value).lower()
        label = re.sub(r"[_/|]+", " ", label)
        label = re.sub(r"\s+", " ", label).strip(" .,:;!?")
        if not label:
            return ""

        label = self.controls["manual_merges"].get(label, label)
        label = self.controls["entity_aliases"].get(label, label)
        return label.strip()

    def _apply_controls(self, candidates: list[str]) -> list[str]:
        normalized = []
        for candidate in candidates:
            term = self.normalize_topic_label(candidate)
            if not term:
                continue
            term = self.controls["manual_merges"].get(term, term)
            if term in self.controls["blocklist"] and term not in self.controls["allowlist"]:
                continue
            normalized.append(term)

        return [
            term
            for term in self._dedupe_preserve_order(normalized)
            if not self._is_noisy_term(term) or term in self.controls["allowlist"]
        ]

    def _is_noisy_term(self, term: str) -> bool:
        token = self.normalize_text(term).lower()
        if not token:
            return True
        if token in self.controls["allowlist"]:
            return False
        if token in self.controls["blocklist"]:
            return True
        if len(token) < 3 or len(token) > 80:
            return True

        alpha_chars = sum(1 for ch in token if ch.isalpha())
        total_chars = len(token.replace(" ", "")) or 1
        alpha_ratio = alpha_chars / total_chars
        if alpha_ratio < 0.6:
            return True

        unique_chars = len(set(token.replace(" ", "")))
        if unique_chars <= 2 and len(token.replace(" ", "")) > 5:
            return True

        if re.search(r"(.)\1\1\1", token):
            return True

        return False

    @staticmethod
    def _dedupe_preserve_order(items: list[str]) -> list[str]:
        seen = set()
        result = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _normalize_entity_alias(self, entity: str) -> str:
        normalized = self.normalize_topic_label(entity)
        return self.controls["entity_aliases"].get(normalized, normalized)

    def _extract_record_text(self, record: dict[str, Any]) -> str:
        keys = [
            "data.title",
            "data.description",
            "data.text",
            "data.summary",
            "data.topic",
            "data.keyword",
            "data.indicator",
            "data.place",
            "data.city",
            "data.weather",
            "title",
            "description",
            "text",
            "summary",
            "topic",
            "keyword",
            "indicator",
            "place",
            "city",
            "disease",
            "event",
            "data_city",
            "data_weather",
        ]
        parts = []
        for key in keys:
            value = self._safe_get(record, key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                parts.append(text)
        return " ".join(self._dedupe_preserve_order(parts)).strip()

    @staticmethod
    def _safe_get(obj: dict[str, Any], key: str) -> Any:
        cursor = obj
        for part in key.split("."):
            if isinstance(cursor, dict):
                cursor = cursor.get(part)
            else:
                return None
        return cursor

    @staticmethod
    def _ensure_data_node(record: dict[str, Any]) -> dict[str, Any]:
        data = record.get("data")
        if isinstance(data, dict):
            return data
        data_node = {}
        if data is not None:
            data_node["raw_data"] = data
        record["data"] = data_node
        return data_node

    def _sentiment_impact(self, text_en: str) -> float:
        if not text_en:
            return 0.0
        try:
            polarity = float(TextBlob(text_en).sentiment.polarity)
            return min(1.0, abs(polarity))
        except Exception:
            return 0.0

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _load_documents_for_topics(self, db, max_docs: int = 240) -> list[dict[str, Any]]:
        source_config = {
            "news": ["data.title", "data.description", "title", "description"],
            "gdelt": ["data.title", "title", "description", "data.description"],
            "reddit": ["data.title", "data.text", "title", "text"],
            "wiki": ["data.summary", "summary", "data.title", "title"],
            "health": ["data.description", "description", "data.indicator", "indicator"],
            "who": ["data.description", "description", "data.indicator", "indicator"],
            "trends": ["data.topic", "data.keyword", "topic", "keyword", "title"],
            "weather": ["data.weather", "weather", "data.city", "city", "title", "description"],
            "earthquakes": ["data.place", "place", "title", "description"],
        }

        per_source = max(20, int(max_docs / max(1, len(source_config))))
        rows: list[dict[str, Any]] = []

        for source, fields in source_config.items():
            try:
                collection = db[source]
                docs = list(collection.find().sort("collected_at", -1).limit(per_source))
            except Exception:
                continue

            for doc in docs:
                text_chunks = []
                for field in fields:
                    value = self._safe_get(doc, field)
                    if value is None:
                        continue
                    chunk = str(value).strip()
                    if chunk:
                        text_chunks.append(chunk)

                text = " ".join(self._dedupe_preserve_order(text_chunks)).strip()
                if not text:
                    continue

                ts = (
                    self._safe_get(doc, "collected_at")
                    or self._safe_get(doc, "timestamp")
                    or self._safe_get(doc, "data.timestamp")
                    or self._safe_get(doc, "data.date")
                )

                sentiment = (
                    self._safe_get(doc, "data.sentiment.textblob.polarity")
                    or self._safe_get(doc, "data.sentiment.polarity")
                    or 0.0
                )

                rows.append(
                    {
                        "text": text,
                        "source": source,
                        "timestamp": ts,
                        "sentiment": sentiment,
                    }
                )

        return rows[:max_docs]

    def _load_spacy_model(self):
        if self._spacy_nlp is not None:
            return self._spacy_nlp

        if spacy is None:
            self._spacy_nlp = None
            return None

        try:
            self._spacy_nlp = spacy.load("en_core_web_sm")
            return self._spacy_nlp
        except Exception:
            self._spacy_nlp = None
            return None

    def _load_keybert_model(self):
        if self._keybert_model is not None:
            return self._keybert_model
        if KeyBERT is None:
            return None
        try:
            self._keybert_model = KeyBERT(model="all-MiniLM-L6-v2")
            return self._keybert_model
        except Exception as exc:
            self._log(f"KeyBERT load warning: {exc}")
            self._keybert_model = None
            return None

    def _load_controls(self, path: str) -> dict[str, Any]:
        controls = dict(DEFAULT_TOPIC_CONTROLS)
        if not path:
            return self._normalize_controls(controls)
        try:
            if not os.path.exists(path):
                return self._normalize_controls(controls)
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                controls.update(payload)
        except Exception as exc:
            self._log(f"Topic controls load warning: {exc}")
        return self._normalize_controls(controls)

    @staticmethod
    def _normalize_controls(controls: dict[str, Any]) -> dict[str, Any]:
        allow = {str(x).strip().lower() for x in controls.get("allowlist", []) if str(x).strip()}
        block = {str(x).strip().lower() for x in controls.get("blocklist", []) if str(x).strip()}
        merges = {
            str(k).strip().lower(): str(v).strip().lower()
            for k, v in dict(controls.get("manual_merges", {})).items()
            if str(k).strip() and str(v).strip()
        }
        aliases = {
            str(k).strip().lower(): str(v).strip().lower()
            for k, v in dict(controls.get("entity_aliases", {})).items()
            if str(k).strip() and str(v).strip()
        }
        return {
            "allowlist": allow,
            "blocklist": block,
            "manual_merges": merges,
            "entity_aliases": aliases,
        }

    def _translation_cache_key(self, text: str, lang: str) -> str:
        digest = hashlib.sha256(f"{lang}:{text}".encode("utf-8", errors="ignore")).hexdigest()
        return digest

    def _translation_cache_get(self, cache_key: str) -> dict[str, Any] | None:
        with self._cache_lock:
            mem_hit = self._translation_cache_mem.get(cache_key)
            if mem_hit is not None:
                return mem_hit

        if self._translation_cache_collection is None:
            return None

        try:
            doc = self._translation_cache_collection.find_one({"cache_key": cache_key})
            if doc:
                with self._cache_lock:
                    self._translation_cache_mem[cache_key] = doc
                return doc
        except Exception:
            return None
        return None

    def _translation_cache_set(self, cache_key: str, payload: dict[str, Any]) -> None:
        with self._cache_lock:
            self._translation_cache_mem[cache_key] = payload

        if self._translation_cache_collection is None:
            return

        try:
            self._translation_cache_collection.update_one(
                {"cache_key": cache_key},
                {"$set": payload},
                upsert=True,
            )
        except Exception:
            pass

    @staticmethod
    def _new_observability_snapshot() -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "docs_processed": 0,
            "language_mix": Counter(),
            "translation_cache_hit": 0,
            "translation_success": 0,
            "translation_failed": 0,
            "translation_skipped": 0,
            "candidate_terms_total": 0,
            "keyphrase_terms_total": 0,
            "entity_terms_total": 0,
            "filtered_low_freq": 0,
            "filtered_noisy": 0,
            "clustering_runs": 0,
            "clustering_failures": 0,
            "top_topics_generated": 0,
        }

    @staticmethod
    def _finalize_observability(observability: dict[str, Any]) -> dict[str, Any]:
        language_mix = observability.get("language_mix", Counter())
        if isinstance(language_mix, Counter):
            observability["language_mix"] = dict(language_mix)

        docs_processed = max(1, int(observability.get("docs_processed", 0)))
        observability["translation_hit_rate"] = round(
            float(observability.get("translation_success", 0) + observability.get("translation_cache_hit", 0))
            / docs_processed,
            4,
        )
        observability["noisy_token_rate"] = round(
            float(observability.get("filtered_noisy", 0))
            / max(1.0, float(observability.get("candidate_terms_total", 0))),
            4,
        )
        return observability

    def _persist_observability(self, observability: dict[str, Any]) -> None:
        if self._observability_collection is None:
            return
        try:
            doc = dict(observability)
            doc["timestamp"] = datetime.now(timezone.utc)
            self._observability_collection.insert_one(doc)
        except Exception as exc:
            self._log(f"Observability persistence warning: {exc}")

    def _log(self, message: str) -> None:
        if self.log_fn is not None:
            try:
                self.log_fn(message)
            except Exception:
                pass

