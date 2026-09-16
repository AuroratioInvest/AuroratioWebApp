export type PublicLanguage = "en" | "fr";

type CompanyInformation = {
  brandName: string;
  brandName_p1: string;
  brandName_p2: string;
  legalCompanyName: string | null;
  legalForm: string | null;
  registrationNumber: string | null;
  registeredOffice: string | null;
  contactEmail: string;
  supportEmail: string;
  trademarkSymbol: string;
};

export const companyInformation: CompanyInformation = {
  brandName: "AuroRatio",
  brandName_p1: "Auro",
  brandName_p2: "Ratio",
  legalCompanyName: null,
  legalForm: null,
  registrationNumber: null,
  registeredOffice: null,
  contactEmail: "contact@auroratio.com",
  supportEmail: "support@auroratio.com",
  trademarkSymbol: "®",
};

export const companyInformationCopy = {
  en: {
    companyHeading: "Company",
    legalCompanyNameLabel: "Legal company name",
    legalFormLabel: "Legal form",
    registrationNumberLabel: "Company registration number",
    registeredOfficeLabel: "Registered office",
    contactEmailLabel: "Contact email",
    supportEmailLabel: "Support email",
    legalCompanyNamePlaceholder: "Legal company information to be completed",
    legalFormPlaceholder: "Legal form to be completed",
    registrationNumberPlaceholder: "Registration details to be completed",
    registeredOfficePlaceholder: "Registered office information to be completed",
  },
  fr: {
    companyHeading: "Société",
    legalCompanyNameLabel: "Raison sociale",
    legalFormLabel: "Forme juridique",
    registrationNumberLabel: "Numéro d’immatriculation",
    registeredOfficeLabel: "Siège social",
    contactEmailLabel: "Email de contact",
    supportEmailLabel: "Email du support",
    legalCompanyNamePlaceholder: "Informations légales de la société à compléter",
    legalFormPlaceholder: "Forme juridique à compléter",
    registrationNumberPlaceholder: "Informations d’immatriculation à compléter",
    registeredOfficePlaceholder: "Informations sur le siège social à compléter",
  },
} as const satisfies Record<PublicLanguage, Record<string, string>>;
