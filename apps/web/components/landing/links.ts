import { API_PUBLIC_URL } from "@/lib/api-config";

/**
 * Every destination a signed-out visitor can click.
 *
 * `/welcome` and its subtree are the only part of the site the proxy lets
 * through without a session (see `proxy.ts`), so anything the public pages link
 * to has to live here: one table, so a page that moves only moves once.
 *
 * `board` is `/login` on purpose. The research board reads scope-filtered data,
 * so the honest call to action is the door it actually opens rather than a
 * promised URL.
 */
export const LINKS = {
  home: "/welcome",
  about: "/welcome/about",
  login: "/login",
  board: "/login",
  /** Deep links into the landing page's own sections. */
  platform: "/welcome#platform",
  how: "/welcome#how",
  contact: "/welcome#contact",
  /** The long form of the same method, on the about page. */
  methodology: "/welcome/about#methodology",
  data: "/welcome/about#data",
  architecture: "/welcome/about#architecture",
  security: "/welcome/about#security",
  limits: "/welcome/about#limits",
  faq: "/welcome/about#faq",
  /**
   * The documentation site, in-app. This used to be the FastAPI Swagger page.
   *
   * The Swagger UI documents request bodies; it does not document the product -
   * what a risk score is made of, which source can never answer a question, how
   * to run the stack or what is deliberately out of scope. Sending a visitor
   * there from a link labelled "Docs" promised a manual and delivered an
   * endpoint index, and it was unreachable for anyone whose API port was not
   * forwarded. The manual now lives under `/welcome`, so it survives the same
   * proxy rule as the rest of the public site and needs no backend at all.
   */
  docs: "/welcome/docs",
  /** Deep links into the docs, one per reader question worth answering first. */
  docs_quickstart: "/welcome/docs#getting-started",
  docs_scoring: "/welcome/docs#scoring",
  docs_sources: "/welcome/docs#data-sources",
  docs_api: "/welcome/docs#api",
  docs_glossary: "/welcome/docs#glossary",
  /** The raw machine contract, kept one click away for anyone integrating. */
  api_reference: `${API_PUBLIC_URL}/docs`,
  api_spec: `${API_PUBLIC_URL}/openapi.json`,
  repo: "https://github.com/TabbyMichael/DeFiScope-AI",
} as const;
