export type AppTheme = "shadcn" | "classic";

export function useTheme() {
  const theme = useState<AppTheme>("app-theme", () => "shadcn");
  function apply(value: AppTheme) {
    theme.value = value;
    if (typeof document !== "undefined") {
      document.documentElement.dataset.theme = value;
      document.documentElement.style.colorScheme = "light";
    }
    if (typeof localStorage !== "undefined") localStorage.setItem("app-theme", value);
  }
  function initialize() {
    const stored = localStorage.getItem("app-theme");
    apply(stored === "classic" ? "classic" : "shadcn");
  }
  return { theme, setTheme: apply, initialize };
}
