// Cloudflare Pages Function — Newsletter signup
// Collects emails from the subscribe form.
//
// Requires KV namespace binding: NEWSLETTER_SUBS
// Set up in Cloudflare dashboard:
//   1. Go to Workers & Pages → KV → Create Namespace "newsletter-subs"
//   2. Go to theshoppersverdict Pages project → Settings → Functions → KV namespace bindings
//   3. Add binding named "NEWSLETTER_SUBS" pointing to "newsletter-subs"
//
// Until KV is bound, this logs emails but can't persist them.

export async function onRequest(context) {
  const { request, env } = context;
  
  if (request.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }
  
  try {
    const formData = await request.formData();
    const email = formData.get('email');
    
    if (!email || !email.includes('@')) {
      return Response.redirect('https://theshoppersverdict.com/?subscribe=invalid', 302);
    }
    
    const cleanEmail = email.trim().toLowerCase();
    const name = formData.get('name') || '';
    const cleanName = name.trim();
    
    // Store in KV if binding exists
    if (env.NEWSLETTER_SUBS) {
      let subs = [];
      try {
        const raw = await env.NEWSLETTER_SUBS.get('subscribers', 'json');
        if (raw) subs = raw;
      } catch (e) {}
      
      const exists = subs.find(s => typeof s === 'string' ? s === cleanEmail : s.email === cleanEmail);
      if (!exists) {
        subs.push(cleanName ? { email: cleanEmail, name: cleanName } : cleanEmail);
        await env.NEWSLETTER_SUBS.put('subscribers', JSON.stringify(subs));
      }
      console.log(`Newsletter subscribed via KV: ${cleanEmail} (${cleanName || 'no name'}, total: ${subs.length})`);
    } else {
      console.log(`Newsletter subscribe: ${cleanEmail} (${cleanName || 'no name'} — KV not bound)`);
    }
    
    return Response.redirect(
      `https://theshoppersverdict.com/?subscribe=success&email=${encodeURIComponent(cleanEmail)}`,
      302
    );
  } catch (err) {
    console.error('Subscribe error:', err);
    return Response.redirect('https://theshoppersverdict.com/?subscribe=error', 302);
  }
}
