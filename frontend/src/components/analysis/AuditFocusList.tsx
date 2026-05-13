import type { AuditFocus } from "../../types/audit";
import { AuditFocusCard } from "./AuditFocusCard";

export function AuditFocusList({
  items,
  activeId,
  onSelect,
}: {
  items: AuditFocus[];
  activeId: string | null;
  onSelect: (focus: AuditFocus) => void;
}) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <AuditFocusCard key={item.id} focus={item} active={activeId === item.id} onSelect={onSelect} />
      ))}
    </div>
  );
}
