/**
 * S.S.I. SHADOW - Edge Worker (Gateway)
 * Cloudflare Worker for event processing at the edge.
 */

export interface Env {
  API_URL: string;
  AUTH_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    
    // Health check
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({ status: 'healthy' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    // Event tracking endpoint
    if (url.pathname === '/v1/events' && request.method === 'POST') {
      try {
        const body = await request.json();
        
        // Process event at edge
        const event = {
          ...body,
          received_at: new Date().toISOString(),
          edge_processed: true
        };
        
        // Forward to API
        const apiResponse = await fetch(`${env.API_URL}/api/events`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': request.headers.get('Authorization') || ''
          },
          body: JSON.stringify(event)
        });
        
        return apiResponse;
      } catch (error) {
        return new Response(JSON.stringify({ error: 'Processing failed' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' }
        });
      }
    }
    
    // Proxy other requests
    return fetch(`${env.API_URL}${url.pathname}${url.search}`, {
      method: request.method,
      headers: request.headers,
      body: request.body
    });
  }
};
