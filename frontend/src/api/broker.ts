import client from "./client";

export type BrokerConnection = {
  id: string;
  broker_name?: string;
  account_name?: string;
  account_id?: string;
  is_active: boolean;
  status: string;
  connected_at?: string | null;
  time_waiting?: number | null;
  can_display_portfolio?: boolean;
  can_execute_trades?: boolean;
  role?: string;
};

export const getConnections = async (): Promise<BrokerConnection[]> => {
  const { data } = await client.get("/broker/connections");
  return data;
};

export const connectBroker = async (): Promise<{
  redirect_url: string;
  role?: string;
  execution_provider?: string;
}> => {
  const { data } = await client.post("/broker/connect");
  return data;
};

export const disconnectBroker = async () => {
  const { data } = await client.delete("/broker/disconnect");
  return data;
};