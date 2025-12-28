// ============================================================================
// S.S.I. SHADOW - PII Normalization Utilities
// ============================================================================
// Following Meta's normalization requirements:
// https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters

/**
 * Normalize email address according to Meta requirements:
 * - Trim leading/trailing whitespace
 * - Convert to lowercase
 * - Remove any spaces
 */
export function normalizeEmail(email: string | undefined | null): string | undefined {
  if (!email || email.trim() === '') {
    return undefined;
  }
  
  return email
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '');
}

/**
 * Normalize phone number to E.164 format:
 * - Remove all non-digit characters
 * - Add country code if missing (default: 55 for Brazil)
 * - Ensure starts with country code
 * 
 * Examples:
 * - (11) 99999-9999 → 5511999999999
 * - +55 11 99999-9999 → 5511999999999
 * - 11999999999 → 5511999999999
 */
export function normalizePhone(phone: string | undefined | null, defaultCountryCode: string = '55'): string | undefined {
  if (!phone || phone.trim() === '') {
    return undefined;
  }
  
  // Remove all non-digit characters except leading +
  let digits = phone.replace(/[^\d+]/g, '');
  
  // Remove leading + if present
  if (digits.startsWith('+')) {
    digits = digits.substring(1);
  }
  
  // Remove leading zeros
  digits = digits.replace(/^0+/, '');
  
  // If doesn't start with country code, add default
  if (!digits.startsWith(defaultCountryCode)) {
    // Check if it might already have a different country code (starts with 1-9 and is long enough)
    if (digits.length <= 11) {
      // Likely a local number without country code
      digits = defaultCountryCode + digits;
    }
  }
  
  // Validate minimum length (country code + area code + number)
  if (digits.length < 10) {
    return undefined;
  }
  
  return digits;
}

/**
 * Normalize name (first name, last name):
 * - Trim whitespace
 * - Convert to lowercase
 * - Remove special characters except letters
 * - Handle accented characters (keep them)
 */
export function normalizeName(name: string | undefined | null): string | undefined {
  if (!name || name.trim() === '') {
    return undefined;
  }
  
  return name
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\s]/gu, '') // Remove non-letter characters except spaces
    .replace(/\s+/g, ' ')        // Normalize spaces
    .trim();
}

/**
 * Normalize city:
 * - Trim whitespace
 * - Convert to lowercase
 * - Remove special characters except letters and spaces
 */
export function normalizeCity(city: string | undefined | null): string | undefined {
  if (!city || city.trim() === '') {
    return undefined;
  }
  
  return city
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\s]/gu, '')
    .replace(/\s+/g, '')  // Remove all spaces for hashing
    .trim();
}

/**
 * Normalize state:
 * - Trim whitespace
 * - Convert to lowercase
 * - For Brazil, convert state names to 2-letter codes
 */
export function normalizeState(state: string | undefined | null): string | undefined {
  if (!state || state.trim() === '') {
    return undefined;
  }
  
  const normalized = state.toLowerCase().trim();
  
  // Brazilian state codes mapping
  const brStates: Record<string, string> = {
    'acre': 'ac',
    'alagoas': 'al',
    'amapá': 'ap',
    'amapa': 'ap',
    'amazonas': 'am',
    'bahia': 'ba',
    'ceará': 'ce',
    'ceara': 'ce',
    'distrito federal': 'df',
    'espírito santo': 'es',
    'espirito santo': 'es',
    'goiás': 'go',
    'goias': 'go',
    'maranhão': 'ma',
    'maranhao': 'ma',
    'mato grosso': 'mt',
    'mato grosso do sul': 'ms',
    'minas gerais': 'mg',
    'pará': 'pa',
    'para': 'pa',
    'paraíba': 'pb',
    'paraiba': 'pb',
    'paraná': 'pr',
    'parana': 'pr',
    'pernambuco': 'pe',
    'piauí': 'pi',
    'piaui': 'pi',
    'rio de janeiro': 'rj',
    'rio grande do norte': 'rn',
    'rio grande do sul': 'rs',
    'rondônia': 'ro',
    'rondonia': 'ro',
    'roraima': 'rr',
    'santa catarina': 'sc',
    'são paulo': 'sp',
    'sao paulo': 'sp',
    'sergipe': 'se',
    'tocantins': 'to',
  };
  
  return brStates[normalized] || normalized.substring(0, 2);
}

/**
 * Normalize ZIP/postal code:
 * - Remove all non-alphanumeric characters
 * - Convert to lowercase
 */
export function normalizeZip(zip: string | undefined | null): string | undefined {
  if (!zip || zip.trim() === '') {
    return undefined;
  }
  
  return zip
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]/gi, '');
}

/**
 * Normalize country to 2-letter ISO code:
 * - Convert common names to ISO codes
 */
export function normalizeCountry(country: string | undefined | null): string | undefined {
  if (!country || country.trim() === '') {
    return undefined;
  }
  
  const normalized = country.toLowerCase().trim();
  
  const countryMap: Record<string, string> = {
    'brazil': 'br',
    'brasil': 'br',
    'united states': 'us',
    'usa': 'us',
    'united states of america': 'us',
    'portugal': 'pt',
    'spain': 'es',
    'espanha': 'es',
    'argentina': 'ar',
    'chile': 'cl',
    'colombia': 'co',
    'mexico': 'mx',
    'méxico': 'mx',
  };
  
  return countryMap[normalized] || normalized.substring(0, 2);
}

/**
 * Normalize external ID:
 * - Trim whitespace
 * - Convert to lowercase
 */
export function normalizeExternalId(id: string | undefined | null): string | undefined {
  if (!id || id.trim() === '') {
    return undefined;
  }
  
  return id.toLowerCase().trim();
}

/**
 * Parse FBC cookie from fbclid query parameter
 * Format: fb.{version}.{creation_time}.{fbclid}
 */
export function parseFBC(fbclid: string | undefined | null, creationTime?: number): string | undefined {
  if (!fbclid || fbclid.trim() === '') {
    return undefined;
  }
  
  const timestamp = creationTime || Date.now();
  return `fb.1.${timestamp}.${fbclid}`;
}

/**
 * Generate FBP cookie value if not provided
 * Format: fb.{version}.{creation_time}.{random_number}
 */
export function generateFBP(existingFbp?: string): string {
  if (existingFbp && existingFbp.startsWith('fb.')) {
    return existingFbp;
  }
  
  const timestamp = Date.now();
  const random = Math.floor(Math.random() * 10000000000);
  return `fb.1.${timestamp}.${random}`;
}

/**
 * Extract fbclid from URL
 */
export function extractFBCLID(url: string | undefined | null): string | undefined {
  if (!url) {
    return undefined;
  }
  
  try {
    const urlObj = new URL(url);
    return urlObj.searchParams.get('fbclid') || undefined;
  } catch {
    // Try regex fallback for malformed URLs
    const match = url.match(/[?&]fbclid=([^&]+)/);
    return match ? match[1] : undefined;
  }
}

/**
 * Extract gclid from URL
 */
export function extractGCLID(url: string | undefined | null): string | undefined {
  if (!url) {
    return undefined;
  }
  
  try {
    const urlObj = new URL(url);
    return urlObj.searchParams.get('gclid') || undefined;
  } catch {
    const match = url.match(/[?&]gclid=([^&]+)/);
    return match ? match[1] : undefined;
  }
}

/**
 * Extract ttclid from URL
 */
export function extractTTCLID(url: string | undefined | null): string | undefined {
  if (!url) {
    return undefined;
  }
  
  try {
    const urlObj = new URL(url);
    return urlObj.searchParams.get('ttclid') || undefined;
  } catch {
    const match = url.match(/[?&]ttclid=([^&]+)/);
    return match ? match[1] : undefined;
  }
}
