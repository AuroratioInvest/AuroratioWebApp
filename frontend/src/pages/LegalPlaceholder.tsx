import { Link } from "react-router-dom";
import PublicFooter from "../components/PublicFooter";
import { usePublicLanguage } from "../context/PublicLanguageContext";


type LegalPlaceholderProps = {
  documentName: string;
  documentNameFr: string;
};


export default function LegalPlaceholder({
  documentName,
  documentNameFr,
}: LegalPlaceholderProps) {
  const { language, setLanguage } = usePublicLanguage();

  return (
    <div style={{ background: "#0A0A08" }}>
      <main
        style={{
          minHeight: "70vh",
          background: "#0A0A08",
          color: "#E8E4D8",
          fontFamily: "DM Sans, sans-serif",
          padding: "3rem 1.5rem 6rem",
        }}
      >
        <div style={{ maxWidth: "760px", margin: "0 auto" }}>
          <nav
            aria-label={language === "fr" ? "Navigation juridique" : "Legal navigation"}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "1rem",
              marginBottom: "5rem",
            }}
          >
            <Link to="/" style={{ color: "#C9A84C", textDecoration: "none" }}>
              AuroRatio
            </Link>
            <div
              role="group"
              aria-label={language === "fr" ? "Sélection de la langue" : "Language selector"}
            >
              <button
                type="button"
                onClick={() => setLanguage("en")}
                aria-pressed={language === "en"}
              >
                EN
              </button>{" "}
              <button
                type="button"
                onClick={() => setLanguage("fr")}
                aria-pressed={language === "fr"}
              >
                FR
              </button>
            </div>
          </nav>

          <p style={{ color: "#C9A84C", textTransform: "uppercase" }}>
            {language === "fr" ? "Document juridique" : "Legal document"}
          </p>
          <h1 style={{ fontFamily: "Cormorant Garamond, serif", fontSize: "3rem" }}>
            {language === "fr" ? documentNameFr : documentName}
          </h1>
          <p style={{ color: "#A5A08E", lineHeight: 1.7 }}>
            {language === "fr"
              ? "Contenu provisoire. Ce document est en attente de revue juridique et ne constitue pas un texte juridique approuvé."
              : "Placeholder content. This document is pending legal review and is not approved legal text."}
          </p>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
