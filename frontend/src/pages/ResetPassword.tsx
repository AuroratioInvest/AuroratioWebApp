import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import client from "../api/client";

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!token) {
      setError("Missing reset token.");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      await client.post("/auth/reset-password", {
        token,
        password,
      });

      setSuccess("Your password has been updated. You can now sign in.");
      setTimeout(() => navigate("/login", { replace: true }), 1200);
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          "Could not reset your password. The link may be invalid or expired."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

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

        .wordmark {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.7rem;
          text-decoration: none;
          color: var(--text);
        }

        .wordmark span { color: var(--gold-light); }

        .header-link,
        .text-link {
          color: var(--text-muted);
          text-decoration: none;
          transition: color .2s;
        }

        .header-link:hover,
        .text-link:hover {
          color: var(--gold-light);
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
          max-width: 460px;
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
          font-size: .95rem;
        }

        .auth-form {
          display: grid;
          gap: 1.1rem;
        }

        .form-group {
          display: grid;
          gap: .45rem;
        }

        .form-label {
          font-size: .75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: .08em;
        }

        .form-input {
          width: 100%;
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

        .auth-button {
          border-radius: 5px;
          padding: 1rem 1.3rem;
          font-family: 'DM Sans', sans-serif;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: .06em;
          cursor: pointer;
          border: 0;
          background: var(--gold);
          color: var(--ink);
        }

        .auth-button:hover:not(:disabled) {
          background: var(--gold-light);
        }

        .auth-button:disabled {
          opacity: .55;
          cursor: not-allowed;
        }

        .error-message,
        .success-message {
          border-radius: 5px;
          padding: .85rem 1rem;
          font-size: .88rem;
          line-height: 1.5;
        }

        .error-message {
          background: rgba(239,83,80,.1);
          border: 1px solid rgba(239,83,80,.28);
          color: #EF8A85;
        }

        .success-message {
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
          .auth-header { padding: 1.2rem 1.5rem; }
          .auth-card { padding: 2rem; }
          .auth-title { font-size: 2.3rem; }
        }
      `}</style>

      <header className="auth-header">
        <Link to="/" className="wordmark">
          <span>Auro</span>Ratio
        </Link>

        <Link to="/login" className="header-link">
          Back to sign in
        </Link>
      </header>

      <main className="auth-container">
        <section className="auth-card">
          <p className="auth-eyebrow">New password</p>
          <h1 className="auth-title">Choose password</h1>
          <p className="auth-subtitle">
            Enter your new password below. It must contain at least 8 characters.
          </p>

          <form className="auth-form" onSubmit={handleSubmit}>
            {error && <div className="error-message">{error}</div>}
            {success && <div className="success-message">{success}</div>}

            <div className="form-group">
              <label className="form-label">New password</label>
              <input
                className="form-input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Confirm password</label>
              <input
                className="form-input"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />
            </div>

            <button className="auth-button" type="submit" disabled={loading}>
              {loading ? "Updating..." : "Update password"}
            </button>
          </form>

          <div className="auth-footer">
            <Link to="/login" className="text-link">
              Return to sign in
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}