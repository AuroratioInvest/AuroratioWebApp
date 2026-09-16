import client from "./client";

export type AdminFaUser = {
  user_id: string;
  email: string;
  is_active: boolean;
  trading_enabled: boolean;
  preferred_trading_provider?: string | null;
  fa_status?: string | null;
  ibkr_client_account_id?: string | null;
  advisor_master_account_id?: string | null;
  mapping_active?: boolean;
  mapping_trading_enabled?: boolean;
  bot_state_trading_enabled?: boolean;
};

export type IBKRMappingPayload = {
  user_id: string;
  advisor_master_account_id: string;
  ibkr_client_account_id: string;
  account_alias?: string | null;
  base_currency?: string;
  is_active?: boolean;
  trading_enabled?: boolean;
};

export type TradingControlsPayload = {
  trading_enabled?: boolean;
  preferred_trading_provider?: string;
  m1_enabled?: boolean;
  m2_enabled?: boolean;
  m3_enabled?: boolean;
};

export type ModulePositionPayload = {
  metal?: string;
  etf_symbol?: string;
  quantity?: number;
  last_value_chf?: number;
  last_fill_price?: number;
  is_enabled?: boolean;
};

export async function getFaUsers(): Promise<AdminFaUser[]> {
  const res = await client.get("/admin/fa/users");
  return res.data;
}

export async function getFaUserDetail(userId: string) {
  const res = await client.get(`/admin/fa/users/${userId}`);
  return res.data;
}

export async function createFaAuthorization(payload: {
  user_id: string;
  advisor_master_account_id?: string;
  ibkr_client_account_id?: string;
  authorization_reference?: string;
  notes?: string;
}) {
  const res = await client.post("/admin/fa/authorizations", payload);
  return res.data;
}

export async function updateFaAuthorization(
  userId: string,
  payload: {
    status?: string;
    advisor_master_account_id?: string;
    ibkr_client_account_id?: string;
    authorization_reference?: string;
    notes?: string;
  }
) {
  const res = await client.patch(`/admin/fa/authorizations/${userId}`, payload);
  return res.data;
}

export async function activateFaAuthorization(
  userId: string,
  payload: IBKRMappingPayload
) {
  const res = await client.post(
    `/admin/fa/authorizations/${userId}/activate`,
    payload
  );

  return res.data;
}

export async function createOrUpdateIbkrMapping(payload: IBKRMappingPayload) {
  const res = await client.post("/admin/fa/mappings", payload);
  return res.data;
}

export async function updateIbkrMapping(
  userId: string,
  payload: Partial<IBKRMappingPayload>
) {
  const res = await client.patch(`/admin/fa/mappings/${userId}`, payload);
  return res.data;
}

export async function updateTradingControls(
  userId: string,
  payload: TradingControlsPayload
) {
  const res = await client.patch(
    `/admin/fa/users/${userId}/trading-controls`,
    payload
  );

  return res.data;
}

export async function enableUserTrading(userId: string) {
  const res = await client.post(`/admin/fa/users/${userId}/enable-trading`);
  return res.data;
}

export async function disableUserTrading(userId: string) {
  const res = await client.post(`/admin/fa/users/${userId}/disable-trading`);
  return res.data;
}

export async function getAdminModulePositions(userId: string) {
  const res = await client.get(`/admin/fa/users/${userId}/module-positions`);
  return res.data;
}

export async function updateAdminModulePosition(
  positionId: string,
  payload: ModulePositionPayload
) {
  const res = await client.patch(
    `/admin/fa/module-positions/${positionId}`,
    payload
  );

  return res.data;
}