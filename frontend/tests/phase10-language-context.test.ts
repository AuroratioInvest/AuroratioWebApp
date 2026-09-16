import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

const providerSource = await read("../src/context/PublicLanguageContext.tsx");
const mainSource = await read("../src/main.tsx");
const headerSource = await read("../src/components/PublicHeader.tsx");
const footerSource = await read("../src/components/PublicFooter.tsx");

const sharedPublicPages = await Promise.all(
  ["Landing", "Contact", "Platform", "Performance"].map((name) =>
    read(`../src/pages/${name}.tsx`)
  )
);

const accountlessPages = await Promise.all(
  ["ManageSubscription", "SubscriptionOutcome", "LegalPlaceholder"].map((name) =>
    read(`../src/pages/${name}.tsx`)
  )
);

test("one provider owns public language persistence and document metadata", () => {
  assert.match(mainSource, /<PublicLanguageProvider>/);
  assert.match(providerSource, /useState<PublicLanguage>\(readStoredLanguage\)/);
  assert.match(providerSource, /localStorage\.setItem\(STORAGE_KEY, language\)/);
  assert.match(providerSource, /document\.documentElement\.lang = language/);
});

test("shared public chrome consumes language context directly", () => {
  assert.match(headerSource, /usePublicLanguage\(\)/);
  assert.match(headerSource, /setLanguage\("en"\)/);
  assert.match(headerSource, /setLanguage\("fr"\)/);
  assert.doesNotMatch(headerSource, /onLanguageChange/);
  assert.match(footerSource, /usePublicLanguage\(\)/);
});

test("public pages no longer maintain independent language state", () => {
  for (const source of [...sharedPublicPages, ...accountlessPages]) {
    assert.match(source, /usePublicLanguage\(\)/);
    assert.doesNotMatch(source, /window\.dispatchEvent\(new Event\("languagechange"\)\)/);
    assert.doesNotMatch(source, /localStorage\.setItem\("language"/);
  }
});
