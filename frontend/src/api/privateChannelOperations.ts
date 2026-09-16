import client from "./client";

export type WorkflowStatusCounts = Record<string, number>;

export type PrivateChannelCounts = {
  total: number;
  active: number;
  configured: number;
  ready: number;
};

export type PrivateChannelOperationsOverview = {
  provider_credentials_configured: boolean;
  private_channel_counts: PrivateChannelCounts;
  active_plan_channel_mapping_count: number;
  access_fulfillment_counts: WorkflowStatusCounts;
  signal_publication_counts: WorkflowStatusCounts;
  approved_signal_count: number;
  draft_signal_count: number;
};

export type PrivateChannelMapping = {
  mapping_id: string;
  plan_id: string;
  plan_code: string | null;
  plan_display_name_en: string | null;
  plan_display_name_fr: string | null;
  is_active: boolean;
};

export type PrivateChannelConfigurationItem = {
  private_channel_id: string;
  channel_code: string | null;
  display_name_en: string | null;
  display_name_fr: string | null;
  is_active: boolean;
  is_configured: boolean;
  is_archived: boolean;
  has_provider_target: boolean;
  is_ready: boolean;
  mappings: PrivateChannelMapping[];
};

export type PrivateChannelConfigurationResponse = {
  items: PrivateChannelConfigurationItem[];
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
};

export async function getPrivateChannelOperationsOverview() {
  const { data } = await client.get<PrivateChannelOperationsOverview>(
    "/admin/private-channel-operations/overview"
  );
  return data;
}

export async function getPrivateChannelConfiguration(input?: {
  limit?: number;
  afterChannelId?: string | null;
}) {
  const { data } = await client.get<PrivateChannelConfigurationResponse>(
    "/admin/private-channel-operations/channel-configuration",
    {
      params: {
        limit: input?.limit,
        after_channel_id: input?.afterChannelId || undefined,
      },
    }
  );
  return data;
}
