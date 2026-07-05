import clsx from "clsx";

export default function PageBackground() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden">
      {/* Base gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-background" />

      {/* Color blobs — NapCat style */}
      <div
        className={clsx(
          "absolute -top-1/4 -left-1/4 w-[600px] h-[600px]",
          "rounded-full opacity-30 blur-[120px]",
          "bg-primary/40"
        )}
      />
      <div
        className={clsx(
          "absolute top-1/2 -right-1/4 w-[500px] h-[500px]",
          "rounded-full opacity-20 blur-[100px]",
          "bg-secondary/40"
        )}
      />
      <div
        className={clsx(
          "absolute -bottom-1/4 left-1/3 w-[400px] h-[400px]",
          "rounded-full opacity-25 blur-[80px]",
          "bg-success/30"
        )}
      />
    </div>
  );
}
