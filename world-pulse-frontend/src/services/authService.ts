import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function login(email: string, password: string) {
  const response = await axios.post(
    `${API_URL}/auth/login`,
    {
      email,
      password,
    },
    {
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  return response.data;
}

export async function register(name: string, email: string, password: string, role: string, organization?: string) {
  const response = await axios.post(
    `${API_URL}/auth/register`,
    {
      name,
      email,
      password,
      role,
      organization,
    },
    {
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  return response.data;
}

export async function forgotPassword(email: string) {
  const response = await axios.post(
    `${API_URL}/auth/forgot-password`,
    {
      email,
    },
    {
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  return response.data;
}

export async function resetPassword(token: string, newPassword: string) {
  const response = await axios.post(
    `${API_URL}/auth/reset-password`,
    {
      token,
      new_password: newPassword,
    },
    {
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  return response.data;
}
