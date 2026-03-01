# -*- coding: utf-8 -*-
"""
Causal Discovery & Root Cause Analysis
=======================================
Identifies causal relationships between features to determine
root causes of crisis events using causal inference algorithms.

Features:
- PC algorithm for causal structure learning
- Causal graph visualization data
- Root cause identification
- Intervention effect estimation

Author: World Pulse ML Team
"""

import os
import sys
import json
import logging
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import itertools

# Configure logging
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "causal_discovery.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg: str):
    """Log event with timestamp"""
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[CAUSAL] {ts} | {msg}", flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")


# ============================================================
# Configuration
# ============================================================
MODEL_DIR = "./models"
os.makedirs(MODEL_DIR, exist_ok=True)

DATA_DIR = "./data"
FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# Feature columns with human-readable names
FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment", 
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

FEATURE_NAMES = {
    "news_sentiment": "News Sentiment",
    "gdelt_sentiment": "GDELT Sentiment",
    "crypto_return": "Crypto Return",
    "crypto_volatility": "Crypto Volatility",
    "stock_return": "Stock Return",
    "stock_volatility": "Stock Volatility",
    "weather_anomaly": "Weather Anomaly"
}

# Significance levels
SIGNIFICANCE_LEVEL = 0.05  # For conditional independence tests


# ============================================================
# Data Loading
# ============================================================
def load_features_data() -> pd.DataFrame:
    """Load hourly features from CSV"""
    if not os.path.exists(FEATURES_CSV):
        log_event(f"❌ Features file not found: {FEATURES_CSV}")
        return create_sample_data()
    
    df = pd.read_csv(FEATURES_CSV)
    
    # Find timestamp column
    time_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
    if time_cols:
        df.rename(columns={time_cols[0]: "timestamp"}, inplace=True)
    
    # Fill missing values
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna(method='ffill').fillna(0)
    
    log_event(f"✅ Loaded {len(df)} rows of feature data")
    return df


def create_sample_data() -> pd.DataFrame:
    """Create sample data for testing"""
    np.random.seed(42)
    n_samples = 200
    
    # Create correlated data to simulate causal relationships
    # news_sentiment -> gdelt_sentiment
    # crypto_volatility -> stock_volatility
    # weather_anomaly -> news_sentiment
    
    news_sentiment = np.random.randn(n_samples) * 0.3
    weather_anomaly = np.random.randn(n_samples) * 0.1
    news_sentiment += weather_anomaly * 0.4  # Weather affects news
    
    gdelt_sentiment = news_sentiment * 0.6 + np.random.randn(n_samples) * 0.2
    
    crypto_volatility = np.random.rand(n_samples) * 0.1 + 0.02
    stock_volatility = crypto_volatility * 0.5 + np.random.rand(n_samples) * 0.03
    
    crypto_return = np.random.randn(n_samples) * 0.05
    stock_return = crypto_return * 0.3 + np.random.randn(n_samples) * 0.02
    
    data = {
        "timestamp": pd.date_range(start="2024-01-01", periods=n_samples, freq="h"),
        "news_sentiment": news_sentiment,
        "gdelt_sentiment": gdelt_sentiment,
        "crypto_return": crypto_return,
        "crypto_volatility": crypto_volatility,
        "stock_return": stock_return,
        "stock_volatility": stock_volatility,
        "weather_anomaly": weather_anomaly,
    }
    
    df = pd.DataFrame(data)
    return df


# ============================================================
# Statistical Tests for Conditional Independence
# ============================================================
def partial_correlation(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    """
    Compute partial correlation between x and y given z
    
    Returns:
        Partial correlation coefficient
    """
    if len(z) == 0:
        return np.corrcoef(x, y)[0, 1]
    
    # Regress x on z
    from sklearn.linear_model import LinearRegression
    reg_x = LinearRegression().fit(z, x)
    residual_x = x - reg_x.predict(z)
    
    # Regress y on z
    reg_y = LinearRegression().fit(z, y)
    residual_y = y - reg_y.predict(z)
    
    # Correlation of residuals
    return np.corrcoef(residual_x, residual_y)[0, 1]


def ci_test(x: np.ndarray, y: np.ndarray, z: np.ndarray, alpha: float = 0.05) -> Tuple[bool, float]:
    """
    Conditional independence test using partial correlation
    
    Args:
        x: First variable
        y: Second variable  
        z: Conditioning set
        alpha: Significance level
        
    Returns:
        (is_independent, p_value)
    """
    if len(x) < 10:
        return True, 1.0
    
    n = len(x)
    r = partial_correlation(x, y, z)
    
    # Fisher's z-transform
    if abs(r) >= 1:
        return False, 0.0
    
    z_stat = 0.5 * np.log((1 + r) / (1 - r))
    se = 1 / np.sqrt(n - len(z) - 3)
    p_value = 2 * (1 - np.stats.norm.cdf(abs(z_stat / se)))
    
    is_independent = p_value > alpha
    
    return is_independent, p_value


# ============================================================
# PC Algorithm Implementation
# ============================================================
class CausalGraph:
    """Represents a causal graph structure"""
    
    def __init__(self, nodes: List[str]):
        self.nodes = nodes
        self.edges = set()  # (source, target) directed edges
        self.undirected_edges = set()  # (node1, node2) - direction unknown
        self.orientations = {}  # edge -> direction
        
    def add_edge(self, x: str, y: str, directed: bool = False):
        """Add an edge between two nodes"""
        if x == y:
            return
            
        edge = tuple(sorted([x, y]))
        
        if directed:
            self.edges.add((x, y))
            self.undirected_edges.discard(edge)
            self.orientations[(x, y)] = x + " -> " + y
        else:
            self.undirected_edges.add(edge)
    
    def remove_edge(self, x: str, y: str):
        """Remove an edge between two nodes"""
        edge = tuple(sorted([x, y]))
        self.undirected_edges.discard(edge)
        self.edges = {e for e in self.edges if e != (x, y) and e != (y, x)}
    
    def get_adjacency_matrix(self) -> Dict[str, List[str]]:
        """Get adjacency matrix as dictionary"""
        adj = {node: [] for node in self.nodes}
        
        for source, target in self.edges:
            adj[source].append(target)
        
        return adj
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "nodes": self.nodes,
            "directed_edges": list(self.edges),
            "undirected_edges": list(self.undirected_edges),
            "adjacency": self.get_adjacency_matrix()
        }


def pc_algorithm(data: pd.DataFrame, features: List[str], alpha: float = 0.05) -> CausalGraph:
    """
    PC Algorithm for causal discovery
    
    Args:
        data: DataFrame with feature data
        features: List of feature names to analyze
        alpha: Significance level for CI tests
        
    Returns:
        CausalGraph object representing discovered structure
    """
    log_event(f"🔄 Running PC algorithm on {len(features)} features...")
    
    n = len(features)
    graph = CausalGraph(features)
    
    # Step 1: Start with complete undirected graph
    for i in range(n):
        for j in range(i + 1, n):
            graph.add_edge(features[i], features[j], directed=False)
    
    # Step 2: Remove edges based on conditional independence tests
    # Growing set of conditioning variables
    for size in range(n):
        pairs_to_test = list(graph.undirected_edges)
        
        for x, y in pairs_to_test:
            # Get neighbors of x (excluding y)
            neighbors_x = []
            for edge in graph.undirected_edges:
                if x in edge:
                    neighbor = edge[0] if edge[1] == x else edge[1]
                    if neighbor != y:
                        neighbors_x.append(neighbor)
            for source, target in graph.edges:
                if source == x:
                    neighbors_x.append(target)
                elif target == x:
                    neighbors_x.append(source)
            
            # Test all subsets of size 'size'
            if len(neighbors_x) < size:
                continue
            
            for z_set in itertools.combinations(neighbors_x, size):
                z_data = data[list(z_set)].values
                
                x_data = data[x].values
                y_data = data[y].values
                
                is_indep, p_value = ci_test(x_data, y_data, z_data, alpha)
                
                if is_indep:
                    log_event(f"   {x} ⊥ {y} | {set(z_set)} (p={p_value:.4f})")
                    graph.remove_edge(x, y)
                    break
    
    # Step 3: Orient edges (v-structures)
    # Find v-structures: x -> z <- y where x and y are not adjacent
    for z in features:
        # Find potential parents of z
        potential_parents = []
        for source, target in graph.edges:
            if target == z:
                potential_parents.append(source)
        
        # Check for v-structure
        for i, x in enumerate(potential_parents):
            for y in potential_parents[i + 1:]:
                # Check if x and y are not adjacent
                edge = tuple(sorted([x, y]))
                if edge not in graph.undirected_edges:
                    # This is a v-structure: x -> z <- y
                    # Remove undirected edge if exists
                    for e in list(graph.undirected_edges):
                        if z in e:
                            graph.remove_edge(z, x)
                            graph.remove_edge(z, y)
                    
                    graph.add_edge(x, z, directed=True)
                    graph.add_edge(y, z, directed=True)
                    log_event(f"   Found v-structure: {x} -> {z} <- {y}")
    
    # Step 4: Apply orientation rules (Meek rules)
    # Rule 1: Avoid new v-structures
    changed = True
    while changed:
        changed = False
        
        for x, y in list(graph.undirected_edges):
            # Rule R1: If x -> z and z - y, then orient z -> y
            for z in features:
                if (x, z) in graph.edges and (z, y) in graph.undirected_edges:
                    graph.undirected_edges.discard((x, y))
                    graph.add_edge(z, y, directed=True)
                    changed = True
                    
                # Rule R2: If x -> z -> y and x - y, then orient x -> y
                for z2 in features:
                    if (x, z) in graph.edges and (z, z2) in graph.edges and (x, y) in graph.undirected_edges:
                        graph.undirected_edges.discard((x, y))
                        graph.add_edge(x, y, directed=True)
                        changed = True
    
    log_event(f"✅ PC algorithm completed. Found {len(graph.edges)} directed, {len(graph.undirected_edges)} undirected edges")
    
    return graph


# ============================================================
# Root Cause Analysis
# ============================================================
def identify_root_causes(graph: CausalGraph, effect_node: str) -> List[Dict[str, Any]]:
    """
    Identify root causes for a given effect variable
    
    Args:
        graph: Causal graph
        effect_node: The effect variable to analyze
        
    Returns:
        List of root causes with their paths and strengths
    """
    root_causes = []
    
    # Find all directed paths to the effect
    def find_all_paths(graph: CausalGraph, start: str, end: str, visited: set) -> List[List[str]]:
        paths = []
        
        if start == end:
            return [[start]]
        
        visited.add(start)
        
        # Follow outgoing edges
        for source, target in graph.edges:
            if source == start and target not in visited:
                sub_paths = find_all_paths(graph, target, end, visited.copy())
                for path in sub_paths:
                    paths.append([start] + path)
        
        return paths
    
    # Find all ancestors
    ancestors = set()
    def find_ancestors(node: str):
        for source, target in graph.edges:
            if target == node:
                ancestors.add(source)
                find_ancestors(source)
    
    find_ancestors(effect_node)
    
    # Compute causal strength for each ancestor
    for cause in ancestors:
        paths = find_all_paths(graph, cause, effect_node, set())
        
        # Simple strength: longer paths = weaker effect
        if paths:
            avg_path_length = np.mean([len(p) for p in paths])
            strength = 1.0 / avg_path_length
            
            root_causes.append({
                "cause": cause,
                "cause_name": FEATURE_NAMES.get(cause, cause),
                "paths": paths,
                "n_paths": len(paths),
                "strength": float(strength),
                "is_direct": any(len(p) == 2 for p in paths)
            })
    
    # Sort by strength
    root_causes.sort(key=lambda x: -x["strength"])
    
    return root_causes


def compute_causal_effects(data: pd.DataFrame, graph: CausalGraph) -> Dict[str, Dict[str, float]]:
    """
    Estimate causal effects using regression-based approach
    
    Returns:
        Dictionary of causal effects between variables
    """
    from sklearn.linear_model import LinearRegression
    
    effects = {}
    
    for target in graph.nodes:
        # Find direct causes
        parents = [source for source, t in graph.edges if t == target]
        
        if not parents:
            continue
            
        # Fit regression
        X = data[parents].values
        y = data[target].values
        
        try:
            reg = LinearRegression().fit(X, y)
            
            effects[target] = {
                parent: float(coef)
                for parent, coef in zip(parents, reg.coef_)
            }
        except Exception as e:
            log_event(f"⚠️ Failed to compute causal effect for {target}: {e}")
    
    return effects


# ============================================================
# Causal Discovery Main Class
# ============================================================
class CausalDiscovery:
    """
    Causal Discovery and Root Cause Analysis
    
    Features:
    - PC algorithm for structure learning
    - Root cause identification
    - Causal effect estimation
    - Explanation generation
    """
    
    def __init__(self):
        self.graph = None
        self.data = None
        self.causal_effects = {}
        self.root_causes_cache = {}
        
    def discover_structure(self, df: pd.DataFrame, force: bool = False) -> Dict[str, Any]:
        """
        Discover causal structure from data
        
        Args:
            df: DataFrame with feature data
            force: Whether to re-compute even if cached
            
        Returns:
            Causal structure information
        """
        log_event("🔄 Discovering causal structure...")
        
        self.data = df[FEATURE_COLUMNS]
        
        try:
            # Run PC algorithm
            self.graph = pc_algorithm(self.data, FEATURE_COLUMNS, alpha=SIGNIFICANCE_LEVEL)
            
            # Compute causal effects
            self.causal_effects = compute_causal_effects(self.data, self.graph)
            
            # Pre-compute root causes for each feature
            for feature in FEATURE_COLUMNS:
                self.root_causes_cache[feature] = identify_root_causes(self.graph, feature)
            
            result = {
                "status": "success",
                "graph": self.graph.to_dict(),
                "causal_effects": self.causal_effects,
                "n_directed_edges": len(self.graph.edges),
                "n_undirected_edges": len(self.graph.undirected_edges),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            log_event(f"✅ Causal discovery completed: {len(self.graph.edges)} directed, {len(self.graph.undirected_edges)} undirected edges")
            
            return result
            
        except Exception as e:
            log_event(f"❌ Causal discovery failed: {e}")
            traceback.print_exc()
            return {"status": "error", "error": str(e)}
    
    def get_root_causes(self, effect: str) -> List[Dict[str, Any]]:
        """
        Get root causes for a specific effect variable
        
        Args:
            effect: The effect variable name
            
        Returns:
            List of root causes
        """
        if effect not in self.root_causes_cache:
            if self.graph:
                self.root_causes_cache[effect] = identify_root_causes(self.graph, effect)
            else:
                return []
        
        return self.root_causes_cache[effect]
    
    def explain_risk_increase(self, df: pd.DataFrame, feature_changes: Dict[str, float]) -> Dict[str, Any]:
        """
        Explain why risk increased based on feature changes
        
        Args:
            df: Current data
            feature_changes: Dictionary of feature changes
            
        Returns:
            Explanation of causal factors
        """
        if not self.graph:
            return {"error": "No causal graph available. Run discover_structure first."}
        
        explanations = []
        
        # For each changed feature, find downstream effects
        for changed_feature, change_value in feature_changes.items():
            if abs(change_value) < 0.01:  # Skip small changes
                continue
            
            # Find all effects of this change
            affected = []
            
            # Direct effects
            for source, target in self.graph.edges:
                if source == changed_feature:
                    effect_strength = self.causal_effects.get(target, {}).get(changed_feature, 0)
                    affected.append({
                        "feature": target,
                        "feature_name": FEATURE_NAMES.get(target, target),
                        "type": "direct",
                        "effect_strength": effect_strength,
                        "contribution": effect_strength * change_value
                    })
            
            # Aggregate contributions
            total_impact = sum(a["contribution"] for a in affected)
            
            if affected:
                explanations.append({
                    "cause": changed_feature,
                    "cause_name": FEATURE_NAMES.get(changed_feature, changed_feature),
                    "change": change_value,
                    "affected_features": affected,
                    "total_impact": total_impact
                })
        
        # Sort by total impact
        explanations.sort(key=lambda x: -abs(x["total_impact"]))
        
        return {
            "explanations": explanations,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_causal_summary(self) -> Dict[str, Any]:
        """Get summary of causal relationships"""
        if not self.graph:
            return {"error": "No causal graph available"}
        
        # Build summary
        summary = {
            "key_drivers": [],
            "most_affected": [],
            "relationships": []
        }
        
        # Find key drivers (nodes with no incoming directed edges)
        has_incoming = {target for _, target in self.graph.edges}
        key_drivers = [n for n in self.graph.nodes if n not in has_incoming]
        
        summary["key_drivers"] = [
            {"feature": f, "name": FEATURE_NAMES.get(f, f)}
            for f in key_drivers
        ]
        
        # Find most affected (nodes with no outgoing directed edges)
        has_outgoing = {source for source, _ in self.graph.edges}
        most_affected = [n for n in self.graph.nodes if n not in has_outgoing]
        
        summary["most_affected"] = [
            {"feature": f, "name": FEATURE_NAMES.get(f, f)}
            for f in most_affected
        ]
        
        # List relationships
        for source, target in self.graph.edges:
            effect = self.causal_effects.get(target, {}).get(source, 0)
            summary["relationships"].append({
                "source": source,
                "source_name": FEATURE_NAMES.get(source, source),
                "target": target,
                "target_name": FEATURE_NAMES.get(target, target),
                "effect": effect
            })
        
        return summary


# ============================================================
# API Functions
# ============================================================
def discover_causal_structure(df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function for causal discovery"""
    try:
        if df is None:
            df = load_features_data()
        
        discovery = CausalDiscovery()
        result = discovery.discover_structure(df)
        
        return result
        
    except Exception as e:
        log_event(f"❌ Causal discovery API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def get_root_causes_api(effect: str, df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function to get root causes"""
    try:
        if df is None:
            df = load_features_data()
        
        discovery = CausalDiscovery()
        discovery.discover_structure(df)
        
        root_causes = discovery.get_root_causes(effect)
        
        return {
            "status": "success",
            "effect": effect,
            "effect_name": FEATURE_NAMES.get(effect, effect),
            "root_causes": root_causes,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Root causes API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


def explain_risk_change_api(feature_changes: Dict[str, float], df: pd.DataFrame = None) -> Dict[str, Any]:
    """API function to explain risk changes"""
    try:
        if df is None:
            df = load_features_data()
        
        discovery = CausalDiscovery()
        discovery.discover_structure(df)
        
        explanation = discovery.explain_risk_increase(df, feature_changes)
        
        return {
            "status": "success",
            "explanation": explanation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log_event(f"❌ Risk explanation API error: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "error"}


# ============================================================
# Main / Testing
# ============================================================
if __name__ == "__main__":
    log_event("=" * 60)
    log_event("Causal Discovery - Standalone Test Run")
    log_event("=" * 60)
    
    # Load data
    df = load_features_data()
    print(f"\n📊 Loaded {len(df)} rows of data")
    
    # Run causal discovery
    discovery = CausalDiscovery()
    
    print("\n🔄 Running causal discovery...")
    result = discovery.discover_structure(df)
    print(f"   Status: {result.get('status')}")
    print(f"   Directed edges: {result.get('n_directed_edges')}")
    print(f"   Undirected edges: {result.get('n_undirected_edges')}")
    
    # Show causal summary
    print("\n📋 Causal Summary:")
    summary = discovery.get_causal_summary()
    print(f"   Key Drivers: {[d['name'] for d in summary.get('key_drivers', [])]}")
    print(f"   Most Affected: {[d['name'] for d in summary.get('most_affected', [])]}")
    
    print("\n🔗 Causal Relationships:")
    for rel in summary.get("relationships", [])[:5]:
        print(f"   {rel['source_name']} -> {rel['target_name']} (effect: {rel['effect']:.3f})")
    
    # Test root causes
    print("\n🎯 Root causes for news_sentiment:")
    causes = discovery.get_root_causes("news_sentiment")
    for cause in causes[:3]:
        print(f"   {cause['cause_name']}: strength={cause['strength']:.3f}, direct={cause['is_direct']}")
    
    # Test risk explanation
    print("\n💡 Explaining risk changes:")
    changes = {"crypto_volatility": 0.5, "news_sentiment": -0.3}
    explanation = discovery.explain_risk_increase(df, changes)
    for exp in explanation.get("explanations", [])[:2]:
        print(f"   {exp['cause_name']}: impact={exp['total_impact']:.3f}")
    
    log_event("✅ Causal discovery test completed")
