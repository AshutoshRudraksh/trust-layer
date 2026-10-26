export interface RoutedContextNote {
  from_agent: string;
  task_summary: string;
  context_note: string;
  routed_at: string;
}

export interface PriorityRoomItem {
  item_id: string;
  category: "pending_approval" | "active_task_lock" | "specialist_finding";
  title: string;
  owner_agent: string;
  priority_score: number;
  resource_key: string;
  requires_approval: boolean;
  approval_id?: string | null;
  exact_text_preview?: string | null;
  unified_diff?: string | null;
  routed_notes: RoutedContextNote[];
}
