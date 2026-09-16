// shared-styles.css - SHARED STYLES FOR LANDING, PLATFORM, PERFORMANCE
// Import this in all 3 pages to ensure consistency

export const sharedStyles = `
  @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

  /* ============================================
     RESET & BASE
     ============================================ */
  *, *::before, *::after { 
    box-sizing: border-box; 
    margin: 0; 
    padding: 0; 
  }

  html { scroll-behavior: smooth; }

  /* ============================================
     CSS VARIABLES (Platform Design System)
     ============================================ */
  :root {
    --gold: #C9A84C;
    --gold-light: #E8C97A;
    --gold-dark: #8B6914;
    --ink: #0A0A08;
    --ink-2: #111109;
    --ink-3: #1A1A14;
    --ink-4: #242418;
    --text: #E8E4D8;
    --text-muted: #8A8670;
    --rule: rgba(201,168,76,.18);
    --surface: var(--ink-2);
    --surface2: var(--ink-3);
    --border: var(--rule);
    --r: 4px;
    --r-lg: 10px;
  }

  /* ============================================
     NOISE TEXTURE OVERLAY
     ============================================ */
  .page-wrapper::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 0;
    opacity: 0.4;
  }

  .page-wrapper {
    font-family: 'DM Sans', sans-serif;
    background: var(--ink);
    color: var(--text);
    line-height: 1.75;
    overflow-x: hidden;
    -webkit-font-smoothing: antialiased;
  }

  /* ============================================
     NAVIGATION
     ============================================ */
  nav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(10,10,8,0.92);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--rule);
    height: 64px;
  }

  .nav-inner {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 3rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 100%;
  }

  .logo {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.6rem;
    font-weight: 400;
    color: var(--text);
    text-decoration: none;
    transition: color 0.2s;
  }

  .logo span { 
    color: var(--gold); 
  }

  .logo:hover {
    color: var(--gold-light);
  }

  .nav-links {
    display: flex;
    gap: 2.5rem;
    align-items: center;
    list-style: none;
  }

  .nav-link {
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.95rem;
    font-weight: 400;
    transition: color 0.2s;
    position: relative;
  }

  .nav-link:hover {
    color: var(--gold-light);
  }

  .nav-link.active {
    color: var(--gold-light);
  }

  .nav-link.active::after {
    content: '';
    position: absolute;
    bottom: -20px;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--gold);
  }

  .cta-button {
    background: var(--gold);
    color: var(--ink);
    padding: 0.65rem 1.5rem;
    border-radius: var(--r);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.92rem;
    transition: all 0.2s;
    border: none;
    cursor: pointer;
  }

  .cta-button:hover {
    background: var(--gold-light);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(201,168,76,0.25);
  }

  /* ============================================
     TYPOGRAPHY
     ============================================ */
  .section-label {
    font-family: 'Syncopate', sans-serif;
    font-size: 0.6rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 1.2rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    font-weight: 700;
  }

  // .section-label::after {
  //   content: '';
  //   flex: 0 0 40px;
  //   height: 1px;
  //   background: var(--gold);
  // }

  .section-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: clamp(36px, 4vw, 52px);
    font-weight: 300;
    line-height: 1.1;
    color: var(--text);
  }

  .section-title em {
    font-style: italic;
    color: var(--gold);
  }

  .lead {
    font-size: 1.08rem;
    color: var(--text-muted);
    max-width: 640px;
    margin-top: 1.2rem;
    line-height: 1.85;
  }

  /* ============================================
     LAYOUT UTILITIES
     ============================================ */
  .container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 3rem;
  }

  section {
    position: relative;
    z-index: 1;
  }

  /* ============================================
     REVEAL ANIMATIONS
     ============================================ */
  .reveal {
    opacity: 0;
    transform: translateY(30px);
    transition: opacity 0.6s ease, transform 0.6s ease;
  }

  .reveal.in {
    opacity: 1;
    transform: translateY(0);
  }

  /* ============================================
     CHARTS (CONSISTENT SIZING)
     ============================================ */
  .chart-grid {
    display: grid;
    gap: 3rem;
    margin-top: 4rem;
  }

  .chart-box {
    background: var(--surface2);
    border: 1px solid var(--rule);
    border-radius: 8px;
    padding: 32px;
  }

  .chart-box h3 {
    font-family: 'Cormorant Garamond', serif;
    font-size: 24px;
    font-weight: 500;
    color: var(--text);
    margin-bottom: 24px;
  }

  /* CRITICAL: Chart container must have fixed height */
  .chart-box > div {
    height: 350px !important;
  }

  .chart-placeholder {
    background: rgba(200,168,75,0.03);
    border: 1px dashed var(--border);
    height: 320px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 14px;
    border-radius: 4px;
  }

  /* ============================================
     HIGHLIGHT BOXES
     ============================================ */
  .highlight-box {
    background: linear-gradient(135deg, rgba(201,168,76,.1) 0%, rgba(139,105,20,.05) 100%);
    border: 1px solid rgba(201,168,76,.25);
    border-radius: 2px;
    padding: 2rem 2.2rem;
    margin-top: 2rem;
  }

  .highlight-box .hl-label {
    font-family: 'Syncopate', sans-serif;
    font-size: 0.58rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 0.8rem;
    font-weight: 700;
  }

  .highlight-box .hl-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 28px;
    color: var(--text);
    margin-bottom: 1rem;
    font-weight: 400;
  }

  .highlight-box .hl-text {
    color: var(--text-muted);
    line-height: 1.8;
    font-size: 1rem;
  }

  /* ============================================
     FOOTER
     ============================================ */
  footer {
    background: var(--ink);
    border-top: 1px solid var(--rule);
    padding: 3rem 0 2rem;
    margin-top: 8rem;
  }

  .footer-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 2rem;
  }

  .footer-logo {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.5rem;
    color: var(--text);
  }

  .footer-logo span {
    color: var(--gold);
  }

  .footer-links {
    display: flex;
    gap: 2rem;
    list-style: none;
  }

  .footer-link {
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.9rem;
    transition: color 0.2s;
  }

  .footer-link:hover {
    color: var(--gold-light);
  }

  .footer-bottom {
    text-align: center;
    padding-top: 2rem;
    border-top: 1px solid var(--rule);
    color: var(--text-muted);
    font-size: 0.85rem;
  }

  /* ============================================
     RESPONSIVE
     ============================================ */
  @media (max-width: 768px) {
    .container {
      padding: 0 1.5rem;
    }

    .nav-inner {
      padding: 0 1.5rem;
    }

    .nav-links {
      gap: 1.5rem;
    }

    .section-title {
      font-size: 32px;
    }

    .chart-grid {
      grid-template-columns: 1fr;
    }

    .footer-content {
      flex-direction: column;
      gap: 2rem;
    }
  }
`;

export default sharedStyles;
