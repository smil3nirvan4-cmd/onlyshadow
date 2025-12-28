/**
 * S.S.I. SHADOW — Server-Side Cookie Management
 * 
 * Combate restrições do Safari ITP (Intelligent Tracking Prevention):
 * - Safari limita cookies 1st-party JS a 7 dias
 * - Cookies Set-Cookie via HTTP header: 1 ano
 * - Cookies de subdomínio próprio: sem restrição
 * 
 * ESTRATÉGIA:
 * 1. Worker roda em subdomínio próprio (ssi.seudominio.com.br)
 * 2. Cookies são setados via Set-Cookie header
 * 3. Cookies _fbp/_fbc são "promovidos" para server-side
 * 
 * IMPORTANTE: Isso é 100% legítimo e recomendado pela própria Meta
 * https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters
 */

// =============================================================================
// TIPOS
// =============================================================================

export interface CookieConfig {
  name: string;
  value: string;
  maxAge?: number;        // Segundos (default: 90 dias)
  domain?: string;        // Domínio raiz para cross-subdomain
  path?: string;          // Path (default: /)
  secure?: boolean;       // HTTPS only (default: true)
  httpOnly?: boolean;     // Não acessível via JS (default: false para _fbp)
  sameSite?: 'Strict' | 'Lax' | 'None';  // Default: Lax
}

export interface ExtractedCookies {
  ssi_id: string | null;
  fbp: string | null;
  fbc: string | null;
  fbclid: string | null;
  gclid: string | null;
  ttclid: string | null;
  custom: Record<string, string>;
}

// =============================================================================
// CONSTANTES
// =============================================================================

const COOKIE_DEFAULTS = {
  maxAge: 90 * 24 * 60 * 60,  // 90 dias em segundos
  path: '/',
  secure: true,
  httpOnly: false,  // Precisa ser acessível pelo Ghost Script
  sameSite: 'Lax' as const
};

// Cookies que gerenciamos
const MANAGED_COOKIES = ['_ssi_id', '_fbp', '_fbc', '_ssi_consent'];

// =============================================================================
// COOKIE MANAGER
// =============================================================================

export class ServerSideCookieManager {
  private domain: string;
  
  constructor(domain: string) {
    // Extrair domínio raiz (ssi.example.com -> example.com)
    this.domain = this.getRootDomain(domain);
  }
  
  /**
   * Extrai domínio raiz para cookies cross-subdomain
   */
  private getRootDomain(hostname: string): string {
    const parts = hostname.split('.');
    
    // Se for localhost ou IP, retornar como está
    if (parts.length <= 1 || /^\d+$/.test(parts[0])) {
      return hostname;
    }
    
    // Retornar últimos 2 segmentos (example.com)
    // Para domínios como .com.br, retornar últimos 3
    const tlds = ['com.br', 'gov.br', 'org.br', 'co.uk', 'com.au'];
    const lastTwo = parts.slice(-2).join('.');
    
    if (tlds.includes(lastTwo) && parts.length > 2) {
      return parts.slice(-3).join('.');
    }
    
    return lastTwo;
  }
  
  /**
   * Extrai cookies do request
   */
  extractCookies(request: Request): ExtractedCookies {
    const cookieHeader = request.headers.get('Cookie') || '';
    const url = new URL(request.url);
    
    const parsed: Record<string, string> = {};
    
    // Parse cookie header
    cookieHeader.split(';').forEach(cookie => {
      const [name, ...valueParts] = cookie.trim().split('=');
      if (name) {
        parsed[name.trim()] = valueParts.join('=').trim();
      }
    });
    
    // Extrair fbclid/gclid/ttclid da URL
    const fbclid = url.searchParams.get('fbclid');
    const gclid = url.searchParams.get('gclid');
    const ttclid = url.searchParams.get('ttclid');
    
    return {
      ssi_id: parsed['_ssi_id'] || null,
      fbp: parsed['_fbp'] || null,
      fbc: parsed['_fbc'] || this.generateFbc(fbclid),
      fbclid,
      gclid,
      ttclid,
      custom: parsed
    };
  }
  
  /**
   * Gera _fbc a partir de fbclid
   * Formato: fb.1.{timestamp}.{fbclid}
   */
  private generateFbc(fbclid: string | null): string | null {
    if (!fbclid) return null;
    
    const version = 'fb';
    const subdomainIndex = 1;
    const timestamp = Date.now();
    
    return `${version}.${subdomainIndex}.${timestamp}.${fbclid}`;
  }
  
  /**
   * Gera _fbp se não existir
   * Formato: fb.1.{timestamp}.{random}
   */
  private generateFbp(): string {
    const version = 'fb';
    const subdomainIndex = 1;
    const timestamp = Date.now();
    const random = Math.floor(Math.random() * 10000000000);
    
    return `${version}.${subdomainIndex}.${timestamp}.${random}`;
  }
  
  /**
   * Gera SSI ID se não existir
   */
  private generateSsiId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 11);
    return `ssi_${timestamp}_${random}`;
  }
  
  /**
   * Cria string de cookie para Set-Cookie header
   */
  private serializeCookie(config: CookieConfig): string {
    const parts: string[] = [
      `${config.name}=${encodeURIComponent(config.value)}`
    ];
    
    const maxAge = config.maxAge ?? COOKIE_DEFAULTS.maxAge;
    parts.push(`Max-Age=${maxAge}`);
    
    // Usar domínio raiz para cross-subdomain
    if (config.domain || this.domain) {
      parts.push(`Domain=.${config.domain || this.domain}`);
    }
    
    parts.push(`Path=${config.path ?? COOKIE_DEFAULTS.path}`);
    
    if (config.secure ?? COOKIE_DEFAULTS.secure) {
      parts.push('Secure');
    }
    
    if (config.httpOnly ?? COOKIE_DEFAULTS.httpOnly) {
      parts.push('HttpOnly');
    }
    
    parts.push(`SameSite=${config.sameSite ?? COOKIE_DEFAULTS.sameSite}`);
    
    return parts.join('; ');
  }
  
  /**
   * Processa request e retorna cookies a serem setados
   * 
   * LÓGICA:
   * 1. Se _ssi_id não existe → criar
   * 2. Se fbclid na URL e _fbc não existe → criar _fbc
   * 3. Se _fbp não existe → criar
   * 4. Renovar todos os cookies existentes (extend expiry)
   */
  processRequest(request: Request): {
    cookies: ExtractedCookies;
    setCookieHeaders: string[];
    isNew: boolean;
  } {
    const existing = this.extractCookies(request);
    const setCookieHeaders: string[] = [];
    let isNew = false;
    
    // 1. SSI ID
    let ssiId = existing.ssi_id;
    if (!ssiId) {
      ssiId = this.generateSsiId();
      isNew = true;
    }
    
    // Sempre renovar SSI ID
    setCookieHeaders.push(this.serializeCookie({
      name: '_ssi_id',
      value: ssiId,
      maxAge: 365 * 24 * 60 * 60  // 1 ano
    }));
    
    // 2. FBC (se fbclid presente)
    let fbc = existing.fbc;
    if (existing.fbclid && !fbc) {
      fbc = this.generateFbc(existing.fbclid);
    }
    
    if (fbc) {
      setCookieHeaders.push(this.serializeCookie({
        name: '_fbc',
        value: fbc,
        maxAge: 90 * 24 * 60 * 60  // 90 dias
      }));
    }
    
    // 3. FBP
    let fbp = existing.fbp;
    if (!fbp) {
      fbp = this.generateFbp();
    }
    
    // Sempre renovar FBP
    setCookieHeaders.push(this.serializeCookie({
      name: '_fbp',
      value: fbp,
      maxAge: 90 * 24 * 60 * 60  // 90 dias
    }));
    
    return {
      cookies: {
        ssi_id: ssiId,
        fbp,
        fbc,
        fbclid: existing.fbclid,
        gclid: existing.gclid,
        ttclid: existing.ttclid,
        custom: existing.custom
      },
      setCookieHeaders,
      isNew
    };
  }
  
  /**
   * Aplica headers Set-Cookie na response
   */
  applyToResponse(response: Response, setCookieHeaders: string[]): Response {
    // Clonar response para poder modificar headers
    const newResponse = new Response(response.body, response);
    
    // Adicionar cada cookie
    setCookieHeaders.forEach(cookie => {
      newResponse.headers.append('Set-Cookie', cookie);
    });
    
    return newResponse;
  }
}

// =============================================================================
// MIDDLEWARE PARA WORKER
// =============================================================================

/**
 * Middleware que gerencia cookies automaticamente
 * 
 * USO:
 * ```typescript
 * export default {
 *   async fetch(request: Request, env: Env) {
 *     return withCookieManagement(request, env, async (cookies) => {
 *       // Usar cookies.ssi_id, cookies.fbp, etc
 *       return new Response('OK');
 *     });
 *   }
 * }
 * ```
 */
export async function withCookieManagement(
  request: Request,
  env: { COOKIE_DOMAIN?: string },
  handler: (cookies: ExtractedCookies) => Promise<Response>
): Promise<Response> {
  const url = new URL(request.url);
  const domain = env.COOKIE_DOMAIN || url.hostname;
  
  const manager = new ServerSideCookieManager(domain);
  const { cookies, setCookieHeaders, isNew } = manager.processRequest(request);
  
  // Executar handler
  let response = await handler(cookies);
  
  // Aplicar cookies na response
  if (setCookieHeaders.length > 0) {
    response = manager.applyToResponse(response, setCookieHeaders);
  }
  
  return response;
}

// =============================================================================
// UTILIDADES PARA GHOST SCRIPT
// =============================================================================

/**
 * Gera script inline para sincronizar cookies client-side
 * 
 * Útil para garantir que o Ghost Script tenha acesso aos mesmos cookies
 * mesmo se o browser bloquear alguns.
 */
export function generateCookieSyncScript(cookies: ExtractedCookies): string {
  return `
(function() {
  // SSI Cookie Sync
  var cookies = ${JSON.stringify({
    ssi_id: cookies.ssi_id,
    fbp: cookies.fbp,
    fbc: cookies.fbc
  })};
  
  // Salvar em localStorage como backup
  try {
    localStorage.setItem('_ssi_cookies', JSON.stringify(cookies));
  } catch(e) {}
  
  // Expor para Ghost Script
  window._ssi_server_cookies = cookies;
})();
  `.trim();
}

// =============================================================================
// EXPORTS
// =============================================================================

export default {
  ServerSideCookieManager,
  withCookieManagement,
  generateCookieSyncScript
};
