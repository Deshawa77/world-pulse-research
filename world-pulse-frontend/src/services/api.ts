// src/services/api.ts
import axios from "axios";

const API = axios.create({
  baseURL: "http://127.0.0.1:8000", // FastAPI default
  // You can add headers here if needed
  // headers: { 'x-api-key': 'YOUR_API_KEY' }
});

export default API;
