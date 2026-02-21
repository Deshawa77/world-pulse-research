import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "super_secure_api_key";

const API = axios.create({
  baseURL: API_URL,
});

export const API_HEADERS = { "x-api-key": API_KEY };

export default API;
