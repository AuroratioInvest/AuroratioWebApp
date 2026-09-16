import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type PublicLanguage = "en" | "fr";

const STORAGE_KEY = "language";

function readStoredLanguage(): PublicLanguage {
  if (typeof window === "undefined") return "en";
  return window.localStorage.getItem(STORAGE_KEY) === "fr" ? "fr" : "en";
}

type PublicLanguageContextValue = {
  language: PublicLanguage;
  setLanguage: (language: PublicLanguage) => void;
};

const PublicLanguageContext = createContext<PublicLanguageContextValue | null>(null);

export function PublicLanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<PublicLanguage>(readStoredLanguage);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, language);
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(() => ({ language, setLanguage }), [language]);

  return (
    <PublicLanguageContext.Provider value={value}>
      {children}
    </PublicLanguageContext.Provider>
  );
}

export function usePublicLanguage(): PublicLanguageContextValue {
  const context = useContext(PublicLanguageContext);
  if (!context) {
    throw new Error("usePublicLanguage must be used within PublicLanguageProvider");
  }
  return context;
}
