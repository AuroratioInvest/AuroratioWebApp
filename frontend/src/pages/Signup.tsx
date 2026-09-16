import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import client from "../api/client";
import { login } from "../api/auth";
import PhoneInput from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { isValidPhoneNumber } from "libphonenumber-js";

type Language = "en" | "fr";
type SignupStep = "details" | "email" | "phone";

type SignupResponse = {
  access_token?: string;
  token?: string;
  user?: {
    id?: string | number;
    email?: string;
    membership_level?: string;
  };
  user_id?: string | number;
  email?: string;
  membership_level?: string;
};

const copy = {
  en: {
    already: "Already have an account?",
    account: "Account",
    emailVerification: "Email Verification",
    phoneVerification: "Phone Verification",
    subscribe: "Subscribe",
    createEyebrow: "Create your account",
    createTitle: "Start with AuroRatio",
    createSubtitle:
      "Create your secure account first. After verification, you will subscribe and then continue your onboarding.",
    firstName: "First name",
    lastName: "Last name",
    email: "Email",
    birthdate: "Birthdate",
    country: "Country",
    phone: "Phone number (optional)",
    password: "Password",
    confirmPassword: "Confirm password",
    terms:
      "I confirm that I am at least 18 years old and I accept the Terms and Conditions and Privacy Policy.",
    continue: "Continue",
    sending: "Sending code...",
    verifyEmailEyebrow: "Verify your email",
    verifyEmailTitle: "Check your inbox",
    verifyEmailSubtitle: "Enter the verification code sent to",
    code: "Verification code",
    back: "Back",
    verifyContinue: "Verify and continue",
    creating: "Creating account...",
    verifyPhoneEyebrow: "Verify your phone",
    verifyPhoneTitle: "Check your phone",
    verifyPhoneSubtitle: "Enter the SMS verification code sent to",
    sendingSms: "Sending SMS...",
    registered: "Already registered?",
    signIn: "Sign in",
    language: "Language",
    emailSent: "We sent a verification code to your email address.",
    phoneSent: "We sent a verification code to your phone number.",
    devEmail:
      "Development mode: enter 123456 to continue. Add /auth/send-verification and /auth/verify-email on the backend before production.",
    devPhone:
      "Development mode: enter 123456 to continue. Add /auth/send-phone-verification and /auth/verify-phone on the backend before production.",
    errName: "Please enter your first and last name.",
    errEmail: "Please enter your email address.",
    errAge: "You must be at least 18 years old to sign up.",
    errPhone: "Please enter a valid phone number for the selected country.",
    errPassword: "Password must be at least 8 characters.",
    errConfirm: "Passwords do not match.",
    errTerms: "Please accept the terms and conditions.",
    errEmailCode: "Please enter the email verification code.",
    errPhoneCode: "Please enter the phone verification code.",
    errInvalid: "Invalid verification code.",
    errEmailSend: "Could not send the email verification code.",
    errPhoneSend: "Could not send the phone verification code.",
    errSignup: "Signup failed. Please try again.",
  },
  fr: {
    already: "Vous avez déjà un compte ?",
    account: "Compte",
    emailVerification: "Vérification email",
    phoneVerification: "Vérification téléphone",
    subscribe: "Abonnement",
    createEyebrow: "Créer votre compte",
    createTitle: "Commencer avec AuroRatio",
    createSubtitle:
      "Créez d’abord votre compte sécurisé. Après vérification, vous pourrez vous abonner puis continuer votre onboarding.",
    firstName: "Prénom",
    lastName: "Nom",
    email: "Email",
    birthdate: "Date de naissance",
    country: "Pays",
    phone: "Numéro de téléphone (optionnel)",
    password: "Mot de passe",
    confirmPassword: "Confirmer le mot de passe",
    terms:
      "Je confirme avoir au moins 18 ans et j’accepte les Conditions générales et la Politique de confidentialité.",
    continue: "Continuer",
    sending: "Envoi du code...",
    verifyEmailEyebrow: "Vérification email",
    verifyEmailTitle: "Consultez votre boîte mail",
    verifyEmailSubtitle: "Entrez le code de vérification envoyé à",
    code: "Code de vérification",
    back: "Retour",
    verifyContinue: "Vérifier et continuer",
    creating: "Création du compte...",
    verifyPhoneEyebrow: "Vérification téléphone",
    verifyPhoneTitle: "Consultez votre téléphone",
    verifyPhoneSubtitle: "Entrez le code SMS envoyé à",
    sendingSms: "Envoi du SMS...",
    registered: "Déjà inscrit ?",
    signIn: "Se connecter",
    language: "Langue",
    emailSent: "Nous avons envoyé un code de vérification à votre adresse email.",
    phoneSent: "Nous avons envoyé un code de vérification à votre numéro de téléphone.",
    devEmail:
      "Mode développement : entrez 123456 pour continuer. Ajoutez /auth/send-verification et /auth/verify-email côté backend avant la production.",
    devPhone:
      "Mode développement : entrez 123456 pour continuer. Ajoutez /auth/send-phone-verification et /auth/verify-phone côté backend avant la production.",
    errName: "Veuillez entrer votre prénom et votre nom.",
    errEmail: "Veuillez entrer votre adresse email.",
    errAge: "Vous devez avoir au moins 18 ans pour vous inscrire.",
    errPhone: "Veuillez entrer un numéro valide pour le pays sélectionné.",
    errPassword: "Le mot de passe doit contenir au moins 8 caractères.",
    errConfirm: "Les mots de passe ne correspondent pas.",
    errTerms: "Veuillez accepter les conditions générales.",
    errEmailCode: "Veuillez entrer le code de vérification email.",
    errPhoneCode: "Veuillez entrer le code de vérification téléphone.",
    errInvalid: "Code de vérification invalide.",
    errEmailSend: "Impossible d’envoyer le code de vérification email.",
    errPhoneSend: "Impossible d’envoyer le code de vérification téléphone.",
    errSignup: "Inscription échouée. Veuillez réessayer.",
  },
} satisfies Record<Language, Record<string, string>>;

function getStoredLanguage(): Language {
  return localStorage.getItem("language") === "fr" ? "fr" : "en";
}

export default function Signup() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [language, setLanguage] = useState<Language>(getStoredLanguage());
  const text = copy[language];

  const [step, setStep] = useState<SignupStep>("details");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [birthdate, setBirthdate] = useState("");
  const [phone, setPhone] = useState<string | undefined>();
  const [phoneCode, setPhoneCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [emailCode, setEmailCode] = useState("");
  const [verificationSent, setVerificationSent] = useState(false);
  const [phoneVerificationSent, setPhoneVerificationSent] = useState(false);

  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  const normalizedEmail = email.trim().toLowerCase();
  const fullPhoneNumber = phone || "";
  
  const handleLanguageChange = (nextLanguage: Language) => {
    setLanguage(nextLanguage);
    localStorage.setItem("language", nextLanguage);
    window.dispatchEvent(new Event("languagechange"));
  };

  const calculateAge = (value: string) => {
    const today = new Date();
    const birth = new Date(value);
    let age = today.getFullYear() - birth.getFullYear();
    const monthDiff = today.getMonth() - birth.getMonth();

    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
      age -= 1;
    }

    return age;
  };

  const resetSessionState = async () => {
    const lang = localStorage.getItem("language");

    localStorage.removeItem("access_token");
    localStorage.removeItem("user_email");
    localStorage.removeItem("user_id");
    localStorage.removeItem("membership_level");
    localStorage.removeItem("skipped_onboarding");
    localStorage.removeItem("broker_connect_started");
    localStorage.removeItem("broker_connect_time");

    sessionStorage.removeItem("stripe_checkout_started");

    if (lang) localStorage.setItem("language", lang);

    await queryClient.cancelQueries();
    queryClient.clear();
  };

  const storeSession = (data: SignupResponse) => {
    const token = data.access_token || data.token;

    if (token) localStorage.setItem("access_token", token);

    localStorage.setItem("user_email", data.user?.email || data.email || normalizedEmail);

    const userId = data.user?.id || data.user_id;
    if (userId !== undefined && userId !== null) localStorage.setItem("user_id", String(userId));

    const membershipLevel = data.user?.membership_level || data.membership_level;
    if (membershipLevel) localStorage.setItem("membership_level", membershipLevel);

    localStorage.removeItem("skipped_onboarding");
    localStorage.removeItem("broker_connect_started");
    localStorage.removeItem("broker_connect_time");
  };

  const validateDetails = () => {
    if (!firstName.trim() || !lastName.trim()) return text.errName;
    if (!normalizedEmail) return text.errEmail;
    if (!birthdate || calculateAge(birthdate) < 18) return text.errAge;
    if (phone && !isValidPhoneNumber(phone)) return text.errPhone;
    if (password.length < 8) return text.errPassword;
    if (password !== confirmPassword) return text.errConfirm;
    if (!agreed) return text.errTerms;
    return "";
  };

  const requestEmailVerification = async () => {
    setError("");
    setInfo("");

    const validationError = validateDetails();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);

    try {
      await resetSessionState();

      try {
        await client.post("/auth/send-verification", { email: normalizedEmail });
        setInfo(text.emailSent);
      } catch (err: any) {
        if (err.response?.status === 404 || err.response?.status === 405) {
          setInfo(text.devEmail);
        } else {
          throw err;
        }
      }

      setVerificationSent(true);
      setStep("email");
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.message || text.errEmailSend);
    } finally {
      setLoading(false);
    }
  };

  const requestPhoneVerification = async () => {
    setError("");
    setInfo("");
    setLoading(true);

    try {
      try {
        await client.post("/auth/send-phone-verification", {
          phone: fullPhoneNumber,
        });
        setInfo(text.phoneSent);
      } catch (err: any) {
        if (err.response?.status === 404 || err.response?.status === 405) {
          setInfo(text.devPhone);
        } else {
          throw err;
        }
      }

      setPhoneVerificationSent(true);
      setStep("phone");
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.message || text.errPhoneSend);
    } finally {
      setLoading(false);
    }
  };

  const verifyEmailAndContinue = async () => {
    setError("");
    setInfo("");
    setLoading(true);

    try {
      try {
        await client.post("/auth/verify-email", {
          email: normalizedEmail,
          code: emailCode.trim(),
        });
      } catch (err: any) {
        if (err.response?.status === 404 || err.response?.status === 405) {
          if (emailCode.trim() !== "123456") {
            setError(text.errInvalid);
            setLoading(false);
            return;
          }
        } else {
          throw err;
        }
      }

      setLoading(false);
      
      if (!phone) {
        await completeSignup();
      } else {
        await requestPhoneVerification();
      }

    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.message || text.errInvalid);
      setLoading(false);
    }
  };

  const completeSignup = async () => {
    setError("");
    setInfo("");
    setLoading(true);

    try {
      if (phone) {
        try {
          await client.post("/auth/verify-phone", {
            phone: fullPhoneNumber,
            code: phoneCode.trim(),
          });
        } catch (err: any) {
          if (err.response?.status === 404 || err.response?.status === 405) {
            if (phoneCode.trim() !== "123456") {
              setError(text.errInvalid);
              setLoading(false);
              return;
            }
          } else {
            throw err;
          }
        }
      }

      const res = await client.post<SignupResponse>("/auth/signup", {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: normalizedEmail,
        password,
        birthdate,
        phone: phone ? fullPhoneNumber : null,
        email_verified: true,
        phone_verified: Boolean(phone),
      });

      storeSession(res.data);

      if (!localStorage.getItem("access_token")) {
        await login(normalizedEmail, password);
        localStorage.setItem("user_email", normalizedEmail);
      }

      queryClient.clear();
      navigate("/subscribe", { replace: true });
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.message || err.message || text.errSignup);
    } finally {
      setLoading(false);
    }
  };

  const handleDetailsSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await requestEmailVerification();
  };

  const handleEmailSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!emailCode.trim()) {
      setError(text.errEmailCode);
      return;
    }
    await verifyEmailAndContinue();
  };

  const handlePhoneSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!phoneCode.trim()) {
      setError(text.errPhoneCode);
      return;
    }
    await completeSignup();
  };

  const restart = async () => {
    await resetSessionState();
    setStep("details");
    setEmailCode("");
    setPhoneCode("");
    setVerificationSent(false);
    setPhoneVerificationSent(false);
    setError("");
    setInfo("");
  };

  return (
    <div className="auth-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

        .auth-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --ink: #0A0A08;
          --ink-2: #111109;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);
          min-height: 100vh;
          background: var(--ink);
          color: var(--text);
          display: flex;
          flex-direction: column;
          font-family: 'DM Sans', sans-serif;
          position: relative;
        }

        .auth-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: radial-gradient(circle at top, rgba(201,168,76,.08), transparent 32rem);
          pointer-events: none;
        }

        .auth-header {
          position: relative;
          z-index: 2;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          padding: 1.5rem 3rem;
          border-bottom: 1px solid var(--rule);
          background: rgba(10,10,8,.82);
          backdrop-filter: blur(12px);
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .wordmark {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.7rem;
          text-decoration: none;
          color: var(--text);
        }

        .wordmark span { color: var(--gold-light); }

        .header-link, .text-link, .ghost-button {
          color: var(--text-muted);
          text-decoration: none;
          transition: color .2s, border-color .2s, background .2s;
        }

        .header-link:hover, .text-link:hover { color: var(--gold-light); }

        .language-toggle {
          display: inline-flex;
          align-items: center;
          gap: .2rem;
          border: 1px solid var(--rule);
          border-radius: 999px;
          background: rgba(255,255,255,.018);
          padding: .2rem;
        }

        .language-option {
          border: 0;
          background: transparent;
          color: var(--text-muted);
          border-radius: 999px;
          padding: .42rem .58rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .68rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          cursor: pointer;
        }

        .language-option.active {
          background: rgba(201,168,76,.12);
          color: var(--gold);
        }

        .auth-container {
          position: relative;
          z-index: 1;
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
        }

        .auth-card {
          width: 100%;
          max-width: 760px;
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 3rem;
          box-shadow: 0 24px 80px rgba(0,0,0,.35);
        }

        .auth-eyebrow {
          font-family: 'Syncopate', sans-serif;
          text-transform: uppercase;
          font-size: .7rem;
          letter-spacing: .18em;
          color: var(--gold-light);
          margin-bottom: .75rem;
          font-weight: 700;
        }

        .auth-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.75rem;
          font-weight: 400;
          line-height: 1.05;
          margin: 0 0 .6rem;
        }

        .auth-subtitle {
          color: var(--text-muted);
          line-height: 1.6;
          margin: 0 0 2rem;
        }

        .brand-inline {
          color: var(--text);
        }
        
        .brand-inline span {
          color: var(--gold);
        }

        .progress-row {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: .75rem;
          margin-bottom: 2rem;
        }

        .progress-step {
          border: 1px solid var(--rule);
          border-radius: 999px;
          padding: .7rem .9rem;
          min-height: 64px;

          display: flex;
          align-items: center;
          justify-content: center;

          color: var(--text-muted);
          font-size: .75rem;
          text-align: center;
          text-transform: uppercase;
          letter-spacing: .08em;
          line-height: 1.35;
        }

        .progress-step.active {
          border-color: rgba(201,168,76,.45);
          color: var(--gold-light);
          background: rgba(201,168,76,.07);
        }

        .auth-form { display: grid; gap: 1.1rem; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .phone-grid { display: grid; grid-template-columns: 180px 1fr; gap: 1rem; }
        .form-group { display: grid; gap: .45rem; }

        .form-label {
          font-size: .75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: .08em;
        }

        .form-input {
          width: 100%;
          box-sizing: border-box;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .95rem 1rem;
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-size: 1rem;
        }

        .form-input:focus {
          outline: none;
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .phone-input {
          width: 100%;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .95rem 1rem;
          color: var(--text);
        }

        .phone-input:focus-within {
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .phone-input input {
          background: transparent;
          border: 0;
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-size: 1rem;
          outline: none;
        }

        .phone-input select {
          background: var(--ink);
          color: var(--text);
        }

        .phone-input-wrap {
          display: flex;
          align-items: center;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          overflow: hidden;
        }

        .phone-prefix {
          padding: 0 .9rem;
          color: var(--gold-light);
          border-right: 1px solid var(--rule);
          white-space: nowrap;
        }

        .phone-input-wrap .form-input {
          border: 0;
          border-radius: 0;
        }

        .phone-input-wrap:focus-within {
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .verification-code-input {
          padding: 1.25rem 1rem;
          font-size: 2rem;
          text-align: center;
          letter-spacing: .28em;
          font-weight: 600;
        }
          
        .checkbox-row {
          display: flex;
          gap: .75rem;
          color: var(--text-muted);
          font-size: .9rem;
          line-height: 1.5;
        }

        .checkbox-row input { margin-top: .25rem; accent-color: var(--gold); }

        .checkbox-row a {
          color: var(--gold-light);
          text-decoration: none;
        }

        .checkbox-row a:hover { text-decoration: underline; }

        .auth-button, .ghost-button {
          border-radius: 5px;
          padding: 1rem 1.3rem;
          font-family: 'DM Sans', sans-serif;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: .06em;
          cursor: pointer;
        }

        .auth-button {
          border: 0;
          background: var(--gold);
          color: var(--ink);
        }

        .auth-button:hover:not(:disabled) { background: var(--gold-light); }
        .auth-button:disabled, .ghost-button:disabled { opacity: .55; cursor: not-allowed; }

        .ghost-button {
          background: transparent;
          border: 1px solid var(--rule);
        }

        .ghost-button:hover:not(:disabled) {
          color: var(--gold-light);
          border-color: rgba(201,168,76,.45);
          background: rgba(201,168,76,.06);
        }

        .actions-row { display: flex; gap: .8rem; }
        .actions-row .auth-button { flex: 1; }

        .error-message, .info-message {
          border-radius: 5px;
          padding: .85rem 1rem;
          font-size: .88rem;
          line-height: 1.5;
          margin-bottom: 2rem;
        }

        .error-message {
          background: rgba(239,83,80,.1);
          border: 1px solid rgba(239,83,80,.28);
          color: #EF8A85;
        }

        .info-message {
          background: rgba(201,168,76,.08);
          border: 1px solid rgba(201,168,76,.24);
          color: var(--gold-light);
        }

        .auth-footer {
          margin-top: 1.5rem;
          padding-top: 1.5rem;
          border-top: 1px solid var(--rule);
          text-align: center;
          color: var(--text-muted);
          font-size: .9rem;
        }

        @media (max-width: 720px) {
          .auth-header { padding: 1.2rem 1.5rem; flex-wrap: wrap; }
          .auth-card { padding: 2rem; }
          .form-grid, .phone-grid { grid-template-columns: 1fr; }
          .progress-row { grid-template-columns: 1fr; }
          .auth-title { font-size: 2.3rem; }
          .actions-row { flex-direction: column; }
        }
      `}</style>

      <header className="auth-header">
        <Link to="/" className="wordmark">
          <span>Auro</span>Ratio
        </Link>

        <div className="header-actions">
          <div className="language-toggle" aria-label={text.language}>
            <button
              type="button"
              onClick={() => handleLanguageChange("en")}
              className={`language-option ${language === "en" ? "active" : ""}`}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => handleLanguageChange("fr")}
              className={`language-option ${language === "fr" ? "active" : ""}`}
            >
              FR
            </button>
          </div>

          <Link to="/login" className="header-link">
            {text.already}
          </Link>
        </div>
      </header>

      <main className="auth-container">
        <section className="auth-card">
          <div className="progress-row">
            <div className={`progress-step ${step === "details" ? "active" : ""}`}>
              {text.account}
            </div>
            <div className={`progress-step ${step === "email" ? "active" : ""}`}>
              {text.emailVerification}
            </div>
            <div className={`progress-step ${step === "phone" ? "active" : ""}`}>
              {text.phoneVerification}
            </div>
            <div className="progress-step">{text.subscribe}</div>
          </div>

          {step === "details" && (
            <>
              <p className="auth-eyebrow">{text.createEyebrow}</p>
              <h1 className="auth-title">
                {language === "fr" ? "Commencer avec " : "Start with "}
                <span className="brand-inline">
                  <span>Auro</span>Ratio
                </span>
              </h1>
              <p className="auth-subtitle">{text.createSubtitle}</p>

              {error && <div className="error-message">{error}</div>}
              {info && <div className="info-message">{info}</div>}

              <form className="auth-form" onSubmit={handleDetailsSubmit}>
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">{text.firstName}</label>
                    <input className="form-input" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{text.lastName}</label>
                    <input className="form-input" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">{text.email}</label>
                  <input className="form-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </div>

                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">{text.birthdate}</label>
                    <input className="form-input" type="date" value={birthdate} onChange={(e) => setBirthdate(e.target.value)} required />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">{text.phone}</label>
                  <PhoneInput
                    international
                    defaultCountry="FR"
                    value={phone}
                    onChange={setPhone}
                    className="phone-input"
                  />
                </div>
                
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">{text.password}</label>
                    <input className="form-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{text.confirmPassword}</label>
                    <input className="form-input" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
                  </div>
                </div>

                <label className="checkbox-row">
                  <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
                  <span>
                    {language === "fr" ? (
                      <>
                        Je confirme avoir au moins 18 ans et j’accepte les{" "}
                        <a href="/terms" target="_blank" rel="noreferrer">
                          Conditions générales
                        </a>{" "}
                        et la{" "}
                        <a href="/privacy" target="_blank" rel="noreferrer">
                          Politique de confidentialité
                        </a>
                        .
                      </>
                    ) : (
                      <>
                        I confirm that I am at least 18 years old and I accept the{" "}
                        <a href="/terms" target="_blank" rel="noreferrer">
                          Terms and Conditions
                        </a>{" "}
                        and{" "}
                        <a href="/privacy" target="_blank" rel="noreferrer">
                          Privacy Policy
                        </a>
                        .
                      </>
                    )}
                  </span>
                </label>

                <button className="auth-button" type="submit" disabled={loading}>
                  {loading ? text.sending : text.continue}
                </button>
              </form>
            </>
          )}

          {step === "email" && (
            <>
              <p className="auth-eyebrow">{text.verifyEmailEyebrow}</p>
              <h1 className="auth-title">{text.verifyEmailTitle}</h1>
              <p className="auth-subtitle">
                {text.verifyEmailSubtitle} <strong>{normalizedEmail}</strong>.
              </p>

              {error && <div className="error-message">{error}</div>}
              {info && <div className="info-message">{info}</div>}

              <form className="auth-form" onSubmit={handleEmailSubmit}>
                <div className="form-group">
                  <label className="form-label">{text.code}</label>
                  <input
                    className="form-input verification-code-input"
                    inputMode="numeric"
                    maxLength={6}
                    value={emailCode}
                    onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, ""))}
                    placeholder="123456"
                    required
                  />
                </div>

                <div className="actions-row">
                  <button className="ghost-button" type="button" onClick={restart} disabled={loading}>
                    {text.back}
                  </button>
                  <button className="auth-button" type="submit" disabled={loading || !verificationSent}>
                    {loading ? text.sendingSms : text.verifyContinue}
                  </button>
                </div>
              </form>
            </>
          )}

          {step === "phone" && (
            <>
              <p className="auth-eyebrow">{text.verifyPhoneEyebrow}</p>
              <h1 className="auth-title">{text.verifyPhoneTitle}</h1>
              <p className="auth-subtitle">
                {text.verifyPhoneSubtitle} <strong>{fullPhoneNumber}</strong>.
              </p>

              {error && <div className="error-message">{error}</div>}
              {info && <div className="info-message">{info}</div>}

              <form className="auth-form" onSubmit={handlePhoneSubmit}>
                <div className="form-group">
                  <label className="form-label">{text.code}</label>
                  <input
                    className="form-input verification-code-input"
                    inputMode="numeric"
                    maxLength={6}
                    value={phoneCode}
                    onChange={(e) => setPhoneCode(e.target.value.replace(/\D/g, ""))}
                    placeholder="123456"
                    required
                  />
                </div>

                <div className="actions-row">
                  <button className="ghost-button" type="button" onClick={restart} disabled={loading}>
                    {text.back}
                  </button>
                  <button className="auth-button" type="submit" disabled={loading || !phoneVerificationSent}>
                    {loading ? text.creating : text.verifyContinue}
                  </button>
                </div>
              </form>
            </>
          )}

          <div className="auth-footer">
            {text.registered}{" "}
            <Link className="text-link" to="/login">
              {text.signIn}
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}