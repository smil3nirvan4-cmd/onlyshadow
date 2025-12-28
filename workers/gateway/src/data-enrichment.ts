/**
 * S.S.I. SHADOW — Data Enrichment Module
 * 
 * Responsabilidades:
 * - Enriquecer dados de eventos com sinais adicionais
 * - Normalizar e limpar dados de entrada
 * - Hashear PII para CAPI
 * - Validar e formatar dados para cada plataforma
 */

// =============================================================================
// TIPOS
// =============================================================================

export interface RawEventData {
  event_name: string;
  event_id?: string;
  timestamp?: number;
  url?: string;
  referrer?: string;
  
  // User data (pode vir do form ou cookies)
  email?: string;
  phone?: string;
  firstName?: string;
  lastName?: string;
  city?: string;
  state?: string;
  zipCode?: string;
  country?: string;
  
  // Device data
  userAgent?: string;
  ip?: string;
  
  // Meta cookies
  fbp?: string;
  fbc?: string;
  fbclid?: string;
  
  // Google
  gclid?: string;
  
  // TikTok
  ttclid?: string;
  
  // Custom data
  custom_data?: Record<string, any>;
}

export interface EnrichedEventData {
  // Evento
  event_name: string;
  event_id: string;
  event_time: number;
  event_source_url: string;
  action_source: 'website';
  
  // User data (hashed)
  user_data: {
    em?: string[];
    ph?: string[];
    fn?: string;
    ln?: string;
    ct?: string;
    st?: string;
    zp?: string;
    country?: string;
    external_id?: string[];
    client_ip_address?: string;
    client_user_agent?: string;
    fbc?: string;
    fbp?: string;
  };
  
  // Custom data
  custom_data: Record<string, any>;
  
  // Metadata de enriquecimento
  enrichment_metadata: {
    enriched_at: number;
    data_quality_score: number;
    pii_fields_count: number;
    source_fields: string[];
  };
}

// =============================================================================
// HASHING (SHA256)
// =============================================================================

async function sha256(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const dataBuffer = encoder.encode(data.toLowerCase().trim());
  const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// =============================================================================
// DATA CLEANING & NORMALIZATION
// =============================================================================

/**
 * Limpa e normaliza email
 */
function normalizeEmail(email: string): string | null {
  if (!email) return null;
  
  // Remove espaços e converte para lowercase
  let cleaned = email.toLowerCase().trim();
  
  // Validação básica
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(cleaned)) return null;
  
  // Remover dots do Gmail (john.doe@gmail.com = johndoe@gmail.com)
  if (cleaned.includes('@gmail.com')) {
    const [local, domain] = cleaned.split('@');
    cleaned = local.replace(/\./g, '') + '@' + domain;
  }
  
  return cleaned;
}

/**
 * Limpa e normaliza telefone
 */
function normalizePhone(phone: string, countryCode: string = '55'): string | null {
  if (!phone) return null;
  
  // Remove tudo que não é número
  let cleaned = phone.replace(/\D/g, '');
  
  // Se não tem código do país, adiciona
  if (cleaned.length === 10 || cleaned.length === 11) {
    cleaned = countryCode + cleaned;
  }
  
  // Validação: precisa ter entre 12-15 dígitos (com código do país)
  if (cleaned.length < 12 || cleaned.length > 15) return null;
  
  return cleaned;
}

/**
 * Normaliza nome (primeiro ou último)
 */
function normalizeName(name: string): string | null {
  if (!name) return null;
  
  return name
    .toLowerCase()
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // Remove acentos
    .replace(/[^a-z]/g, ''); // Remove caracteres especiais
}

/**
 * Normaliza cidade
 */
function normalizeCity(city: string): string | null {
  if (!city) return null;
  
  return city
    .toLowerCase()
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z\s]/g, '')
    .replace(/\s+/g, '');
}

/**
 * Normaliza estado (BR: sigla de 2 letras)
 */
function normalizeState(state: string): string | null {
  if (!state) return null;
  
  const cleaned = state.toUpperCase().trim();
  
  // Se já é sigla de 2 letras
  if (cleaned.length === 2) {
    return cleaned.toLowerCase();
  }
  
  // Mapeamento de nomes para siglas (BR)
  const stateMap: Record<string, string> = {
    'acre': 'ac', 'alagoas': 'al', 'amapa': 'ap', 'amazonas': 'am',
    'bahia': 'ba', 'ceara': 'ce', 'distrito federal': 'df', 'espirito santo': 'es',
    'goias': 'go', 'maranhao': 'ma', 'mato grosso': 'mt', 'mato grosso do sul': 'ms',
    'minas gerais': 'mg', 'para': 'pa', 'paraiba': 'pb', 'parana': 'pr',
    'pernambuco': 'pe', 'piaui': 'pi', 'rio de janeiro': 'rj', 'rio grande do norte': 'rn',
    'rio grande do sul': 'rs', 'rondonia': 'ro', 'roraima': 'rr', 'santa catarina': 'sc',
    'sao paulo': 'sp', 'sergipe': 'se', 'tocantins': 'to'
  };
  
  const normalized = cleaned
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
  
  return stateMap[normalized] || null;
}

/**
 * Normaliza CEP
 */
function normalizeZipCode(zip: string): string | null {
  if (!zip) return null;
  
  const cleaned = zip.replace(/\D/g, '');
  
  // CEP brasileiro tem 8 dígitos
  if (cleaned.length !== 8) return null;
  
  return cleaned;
}

/**
 * Normaliza país (ISO 3166-1 alpha-2)
 */
function normalizeCountry(country: string): string | null {
  if (!country) return null;
  
  const cleaned = country.toLowerCase().trim();
  
  // Mapeamento comum
  const countryMap: Record<string, string> = {
    'brasil': 'br', 'brazil': 'br', 'br': 'br',
    'estados unidos': 'us', 'eua': 'us', 'usa': 'us', 'united states': 'us',
    'portugal': 'pt', 'pt': 'pt'
  };
  
  return countryMap[cleaned] || cleaned.slice(0, 2);
}

// =============================================================================
// EVENT ID GENERATOR
// =============================================================================

function generateEventId(): string {
  return crypto.randomUUID();
}

// =============================================================================
// DATA QUALITY SCORER
// =============================================================================

interface DataQualityResult {
  score: number;  // 0-1
  piiFields: string[];
  missingRecommended: string[];
  warnings: string[];
}

function assessDataQuality(rawData: RawEventData): DataQualityResult {
  const piiFields: string[] = [];
  const missingRecommended: string[] = [];
  const warnings: string[] = [];
  
  // Verificar PII disponível
  if (rawData.email) piiFields.push('email');
  if (rawData.phone) piiFields.push('phone');
  if (rawData.firstName) piiFields.push('firstName');
  if (rawData.lastName) piiFields.push('lastName');
  if (rawData.city) piiFields.push('city');
  if (rawData.state) piiFields.push('state');
  if (rawData.zipCode) piiFields.push('zipCode');
  if (rawData.country) piiFields.push('country');
  
  // Verificar identificadores Meta
  if (rawData.fbp) piiFields.push('fbp');
  if (rawData.fbc) piiFields.push('fbc');
  if (rawData.fbclid) piiFields.push('fbclid');
  
  // Verificar dados essenciais
  if (!rawData.ip) {
    missingRecommended.push('ip');
    warnings.push('IP ausente - impacta EMQ');
  }
  
  if (!rawData.userAgent) {
    missingRecommended.push('userAgent');
    warnings.push('User Agent ausente - impacta EMQ');
  }
  
  if (!rawData.fbp && !rawData.fbc) {
    missingRecommended.push('fbp/fbc');
    warnings.push('Cookies Meta ausentes - impacta significativamente EMQ');
  }
  
  // Calcular score (baseado em prioridade Meta)
  // Email = +25%, Phone = +20%, fbc = +15%, fbp = +10%, outros = +5% cada
  let score = 0;
  
  if (rawData.email) score += 0.25;
  if (rawData.phone) score += 0.20;
  if (rawData.fbc || rawData.fbclid) score += 0.15;
  if (rawData.fbp) score += 0.10;
  if (rawData.ip) score += 0.10;
  if (rawData.userAgent) score += 0.05;
  if (rawData.firstName || rawData.lastName) score += 0.05;
  if (rawData.city || rawData.state || rawData.zipCode) score += 0.05;
  if (rawData.country) score += 0.05;
  
  return {
    score: Math.min(1, score),
    piiFields,
    missingRecommended,
    warnings
  };
}

// =============================================================================
// MAIN ENRICHMENT FUNCTION
// =============================================================================

export async function enrichEventData(
  rawData: RawEventData,
  additionalContext?: {
    ssiId?: string;
    geoData?: {
      country?: string;
      city?: string;
      region?: string;
    };
  }
): Promise<EnrichedEventData> {
  
  const quality = assessDataQuality(rawData);
  const sourceFields: string[] = [];
  
  // User data hashado
  const userData: EnrichedEventData['user_data'] = {};
  
  // Email
  if (rawData.email) {
    const normalized = normalizeEmail(rawData.email);
    if (normalized) {
      userData.em = [await sha256(normalized)];
      sourceFields.push('email');
    }
  }
  
  // Phone
  if (rawData.phone) {
    const normalized = normalizePhone(rawData.phone);
    if (normalized) {
      userData.ph = [await sha256(normalized)];
      sourceFields.push('phone');
    }
  }
  
  // First Name
  if (rawData.firstName) {
    const normalized = normalizeName(rawData.firstName);
    if (normalized) {
      userData.fn = await sha256(normalized);
      sourceFields.push('firstName');
    }
  }
  
  // Last Name
  if (rawData.lastName) {
    const normalized = normalizeName(rawData.lastName);
    if (normalized) {
      userData.ln = await sha256(normalized);
      sourceFields.push('lastName');
    }
  }
  
  // City (priorizar geo data do Cloudflare)
  const city = additionalContext?.geoData?.city || rawData.city;
  if (city) {
    const normalized = normalizeCity(city);
    if (normalized) {
      userData.ct = await sha256(normalized);
      sourceFields.push('city');
    }
  }
  
  // State (priorizar geo data do Cloudflare)
  const state = additionalContext?.geoData?.region || rawData.state;
  if (state) {
    const normalized = normalizeState(state);
    if (normalized) {
      userData.st = await sha256(normalized);
      sourceFields.push('state');
    }
  }
  
  // Zip Code
  if (rawData.zipCode) {
    const normalized = normalizeZipCode(rawData.zipCode);
    if (normalized) {
      userData.zp = await sha256(normalized);
      sourceFields.push('zipCode');
    }
  }
  
  // Country (priorizar geo data do Cloudflare)
  const country = additionalContext?.geoData?.country || rawData.country;
  if (country) {
    const normalized = normalizeCountry(country);
    if (normalized) {
      userData.country = await sha256(normalized);
      sourceFields.push('country');
    }
  }
  
  // External ID (SSI ID)
  if (additionalContext?.ssiId) {
    userData.external_id = [await sha256(additionalContext.ssiId)];
    sourceFields.push('ssiId');
  }
  
  // IP Address (não hasheado para CAPI)
  if (rawData.ip) {
    userData.client_ip_address = rawData.ip;
    sourceFields.push('ip');
  }
  
  // User Agent (não hasheado para CAPI)
  if (rawData.userAgent) {
    userData.client_user_agent = rawData.userAgent;
    sourceFields.push('userAgent');
  }
  
  // Cookies Meta (não hasheados)
  if (rawData.fbp) {
    userData.fbp = rawData.fbp;
    sourceFields.push('fbp');
  }
  
  if (rawData.fbc) {
    userData.fbc = rawData.fbc;
    sourceFields.push('fbc');
  } else if (rawData.fbclid) {
    // Gerar fbc a partir do fbclid
    const timestamp = Math.floor(Date.now() / 1000);
    userData.fbc = `fb.1.${timestamp}.${rawData.fbclid}`;
    sourceFields.push('fbclid');
  }
  
  // Construir evento enriquecido
  const enrichedEvent: EnrichedEventData = {
    event_name: rawData.event_name,
    event_id: rawData.event_id || generateEventId(),
    event_time: rawData.timestamp ? Math.floor(rawData.timestamp / 1000) : Math.floor(Date.now() / 1000),
    event_source_url: rawData.url || '',
    action_source: 'website',
    
    user_data: userData,
    
    custom_data: {
      ...rawData.custom_data,
      // Adicionar click IDs ao custom_data para tracking
      ...(rawData.fbclid && { fbclid: rawData.fbclid }),
      ...(rawData.gclid && { gclid: rawData.gclid }),
      ...(rawData.ttclid && { ttclid: rawData.ttclid }),
    },
    
    enrichment_metadata: {
      enriched_at: Date.now(),
      data_quality_score: quality.score,
      pii_fields_count: quality.piiFields.length,
      source_fields: sourceFields
    }
  };
  
  return enrichedEvent;
}

// =============================================================================
// PLATFORM-SPECIFIC FORMATTERS
// =============================================================================

/**
 * Formata para Meta CAPI
 */
export function formatForMetaCAPI(enrichedData: EnrichedEventData): Record<string, any> {
  return {
    event_name: enrichedData.event_name,
    event_id: enrichedData.event_id,
    event_time: enrichedData.event_time,
    event_source_url: enrichedData.event_source_url,
    action_source: enrichedData.action_source,
    user_data: enrichedData.user_data,
    custom_data: enrichedData.custom_data
  };
}

/**
 * Formata para Google Enhanced Conversions
 */
export function formatForGoogleEC(enrichedData: EnrichedEventData): Record<string, any> {
  // Mapear eventos para nomenclatura Google
  const eventNameMap: Record<string, string> = {
    'PageView': 'page_view',
    'ViewContent': 'view_item',
    'AddToCart': 'add_to_cart',
    'InitiateCheckout': 'begin_checkout',
    'AddPaymentInfo': 'add_payment_info',
    'Purchase': 'purchase',
    'Lead': 'generate_lead',
    'CompleteRegistration': 'sign_up'
  };
  
  return {
    client_id: enrichedData.user_data.external_id?.[0] || enrichedData.event_id,
    events: [{
      name: eventNameMap[enrichedData.event_name] || enrichedData.event_name.toLowerCase(),
      params: {
        ...enrichedData.custom_data,
        engagement_time_msec: 100
      }
    }],
    user_data: {
      sha256_email_address: enrichedData.user_data.em?.[0],
      sha256_phone_number: enrichedData.user_data.ph?.[0],
      address: {
        sha256_first_name: enrichedData.user_data.fn,
        sha256_last_name: enrichedData.user_data.ln,
        city: enrichedData.user_data.ct,
        region: enrichedData.user_data.st,
        postal_code: enrichedData.user_data.zp,
        country: enrichedData.user_data.country
      }
    }
  };
}

/**
 * Formata para TikTok Events API
 */
export function formatForTikTok(enrichedData: EnrichedEventData): Record<string, any> {
  // Mapear eventos para nomenclatura TikTok
  const eventNameMap: Record<string, string> = {
    'PageView': 'PageView',
    'ViewContent': 'ViewContent',
    'AddToCart': 'AddToCart',
    'InitiateCheckout': 'InitiateCheckout',
    'Purchase': 'CompletePayment',
    'Lead': 'SubmitForm',
    'CompleteRegistration': 'CompleteRegistration'
  };
  
  return {
    event: eventNameMap[enrichedData.event_name] || enrichedData.event_name,
    event_id: enrichedData.event_id,
    timestamp: new Date(enrichedData.event_time * 1000).toISOString(),
    context: {
      user_agent: enrichedData.user_data.client_user_agent,
      ip: enrichedData.user_data.client_ip_address
    },
    user: {
      external_id: enrichedData.user_data.external_id?.[0],
      email: enrichedData.user_data.em?.[0],
      phone_number: enrichedData.user_data.ph?.[0]
    },
    properties: {
      ...enrichedData.custom_data
    }
  };
}

// =============================================================================
// EXPORT
// =============================================================================

export default {
  enrichEventData,
  formatForMetaCAPI,
  formatForGoogleEC,
  formatForTikTok,
  assessDataQuality
};
