export async function onRequest(context) {
  const { request } = context;
  
  if (request.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }
  
  try {
    const formData = await request.formData();
    const email = formData.get('email');
    
    if (!email || !email.includes('@')) {
      return Response.redirect('https://theshoppersverdict.com/?subscribe=invalid', 302);
    }
    
    // Send notification via Migadu SMTP using SendGrid-style HTTP API
    // Since we can't SMTP from a Worker, we'll store to KV or just log
    console.log(`New subscriber: ${email}`);
    
    return Response.redirect(`https://theshoppersverdict.com/?subscribe=success&email=${encodeURIComponent(email)}`, 302);
  } catch (err) {
    console.error('Subscribe error:', err);
    return Response.redirect('https://theshoppersverdict.com/?subscribe=error', 302);
  }
}
