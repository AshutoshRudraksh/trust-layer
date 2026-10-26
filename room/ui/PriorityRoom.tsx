import React from "react";
import { PriorityRoomItem } from "./types";

export interface PriorityRoomProps {
  items: PriorityRoomItem[];
  onDecideApproval: (approvalId: string, decision: "APPROVED" | "DENIED") => void;
}

export const PriorityRoom: React.FC<PriorityRoomProps> = ({ items, onDecideApproval }) => {
  return (
    <section aria-label="Consolidated Priority Room">
      <h2>Consolidated Priority Room</h2>
      {items.length === 0 ? (
        <p>No pending approvals or active specialist locks.</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.item_id} data-testid={`priority-item-${item.item_id}`}>
              <div>
                <strong>[{item.category.toUpperCase()}]</strong> {item.title} (Owner: {item.owner_agent}, Score:{" "}
                {item.priority_score})
              </div>
              {item.exact_text_preview && (
                <pre data-testid="exact-text-preview">{item.exact_text_preview}</pre>
              )}
              {item.unified_diff && (
                <pre data-testid="unified-diff-preview">{item.unified_diff}</pre>
              )}
              {item.routed_notes.length > 0 && (
                <div>
                  <span>Routed specialist context ({item.routed_notes.length}):</span>
                  <ul>
                    {item.routed_notes.map((note, idx) => (
                      <li key={idx}>
                        {note.from_agent}: {note.context_note}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {item.requires_approval && item.approval_id && (
                <div>
                  <button
                    type="button"
                    onClick={() => onDecideApproval(item.approval_id!, "APPROVED")}
                  >
                    Approve Exact Action
                  </button>
                  <button
                    type="button"
                    onClick={() => onDecideApproval(item.approval_id!, "DENIED")}
                  >
                    Deny and Lock Action
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
