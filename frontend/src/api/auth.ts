import client from "./client";

export type UserProfile = {
  id: string;
  email: string;
  membership_level: string;
  is_active: boolean;
  trading_enabled?: boolean;
  preferred_trading_provider?: string;
  created_at?: string;
};

export const getMe = async (): Promise<UserProfile> => {
  const { data } = await client.get("/auth/me");
  return data;
};

export const login = async (email: string, password: string) => {
  const { data } = await client.post("/auth/login", { email, password });

  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("user_email", email);

  try {
    const profile = await getMe();

    localStorage.setItem("membership_level", profile.membership_level);
    localStorage.setItem("user_id", profile.id);
  } catch (err: any) {
    if (err.response?.status === 401 || err.response?.status === 403) {
      localStorage.removeItem("access_token");
    }

    throw new Error("Login failed");
  }

  return data;
};

export const signup = async (payload: {
  first_name?: string;
  last_name?: string;
  email: string;
  password: string;
  birthdate?: string;
  phone?: string | null;
  email_verified?: boolean;
  phone_verified?: boolean;
}) => {
  const { data } = await client.post("/auth/signup", payload);
  return data;
};

export const sendEmailVerification = async (email: string) => {
  const { data } = await client.post("/auth/send-verification", { email });
  return data;
};

export const verifyEmail = async (email: string, code: string) => {
  const { data } = await client.post("/auth/verify-email", { email, code });
  return data;
};

export const sendPhoneVerification = async (phone: string) => {
  const { data } = await client.post("/auth/send-phone-verification", { phone });
  return data;
};

export const verifyPhone = async (phone: string, code: string) => {
  const { data } = await client.post("/auth/verify-phone", { phone, code });
  return data;
};

export const requestPasswordReset = async (email: string) => {
  const { data } = await client.post("/auth/forgot-password", { email });
  return data;
};

export const resetPassword = async (token: string, password: string) => {
  const { data } = await client.post("/auth/reset-password", {
    token,
    password,
  });

  return data;
};

export const getAllUsers = async () =>
  (await client.get("/auth/admin/users")).data;

export const toggleUserActive = async (userId: string) =>
  (await client.patch(`/auth/admin/users/${userId}/toggle-active`)).data;