export function AccentSeparator({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-0 ${className}`}>
      <div className="h-px w-4 bg-primary" />
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}
