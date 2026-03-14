import axios from "axios";
import type { UserRole, UserType } from "./api";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type AuthResponse = {
  access_token: string;
  email: string;
  name: string;
  role: UserRole;
  user_type: UserType;
  message?: string;
};

export async function login(email: string, password: string): Promise<AuthResponse> {
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

  return response.data as AuthResponse;
}

export async function register(
  name: string,
  email: string,
  password: string,
  userType: UserType,
  organization?: string,
  role?: UserRole,
  adminInviteCode?: string
): Promise<AuthResponse> {
  const payload: Record<string, unknown> = {
    name,
    email,
    password,
    user_type: userType,
    organization,
  };

  if (role) {
    payload.role = role;
  }

  if (adminInviteCode) {
    payload.admin_invite_code = adminInviteCode;
  }

  const response = await axios.post(
    `${API_URL}/auth/register`,
    payload,
    {
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  return response.data as AuthResponse;
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
