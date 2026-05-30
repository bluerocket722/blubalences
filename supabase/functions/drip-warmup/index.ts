// supabase/functions/drip-warmup/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Bell curve interval: average of 6 uniforms (Irwin-Hall) scaled to [min, max]
function bellMinutes(min: number, max: number): number {
  let sum = 0;
  for (let i = 0; i < 6; i++) sum += Math.random();
  const t = sum / 6; // ~0.5 center, tapers at edges
  return Math.round(min + t * (max - min));
}

function personalize(body: string, email: string, name: string): string {
  const display = name || email.split("@")[0];
  const parts = display.split(" ");
  const first = parts[0] || display;
  const last = parts.length > 1 ? parts[parts.length - 1] : "";
  const now = new Date();
  const today = now.toLocaleDateString("en-US", { month: "long", day: "2-digit", year: "numeric" });
  const month = now.toLocaleDateString("en-US", { month: "long" });
  return body
    .replace(/\{\{\.?Subscriber\.?FirstName\}\}/g, first)
    .replace(/\{\{\.?Subscriber\.?LastName\}\}/g, last)
    .replace(/\{\{\.?Subscriber\.?Name\}\}/g, display)
    .replace(/\{\{\.?Subscriber\.?Email\}\}/g, email)
    .replace(/\{\{name\}\}/g, display)
    .replace(/\{\{first_name\}\}/g, first)
    .replace(/\{\{last_name\}\}/g, last)
    .replace(/\{\{email\}\}/g, email)
    .replace(/\{\{today\}\}/g, today)
    .replace(/\{\{this_month\}\}/g, month);
}

async function sendBrevo(apiKey: string, from: { email: string; name: string }, to: { email: string; name: string }, subject: string, body: string, inReplyTo?: string) {
  const text = personalize(body, to.email, to.name);
  const html = text.includes("<") ? text : "<html><body>" + text.replace(/\n/g, "<br>") + "</body></html>";
  const payload: Record<string, unknown> = {
    sender: { email: from.email, name: from.name },
    to: [{ email: to.email, name: to.name || to.email }],
    subject,
    htmlContent: html,
    tags: ["warmup"],
  };
  if (inReplyTo) payload.headers = { "In-Reply-To": inReplyTo, References: inReplyTo };
  const r = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: { "api-key": apiKey, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`Brevo ${r.status}: ${await r.text()}`);
  const j = await r.json();
  return j.messageId as string;
}

serve(async () => {
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const sb = createClient(supabaseUrl, supabaseKey);

  // Load global settings
  const { data: settingsRows } = await sb.from("settings").select("key,value");
  const cfg: Record<string, string> = {};
  for (const r of settingsRows || []) cfg[r.key] = r.value?.replace(/^"|"$/g, "") ?? "";

  const brevoKey = cfg.brevo_api_key;
  const fromEmail = cfg.from_email?.match(/^(.+?)\s*<(.+?)>$/)?.[2] ?? cfg.from_email;
  const fromName = cfg.from_name || fromEmail;
  if (!brevoKey || !fromEmail) {
    return new Response(JSON.stringify({ error: "brevo_api_key or from_email not set" }), { status: 500 });
  }

  const now = new Date().toISOString();

  // Find active warm-up sequences
  const { data: sequences } = await sb
    .from("sequences")
    .select("id,name,same_thread,min_interval_minutes,max_interval_minutes")
    .eq("active", true)
    .eq("is_warmup", true);

  const results: string[] = [];

  for (const seq of sequences || []) {
    const minM = seq.min_interval_minutes ?? 5;
    const maxM = seq.max_interval_minutes ?? 15;

    // Get steps for this sequence
    const { data: steps } = await sb
      .from("steps")
      .select("*")
      .eq("sequence_id", seq.id)
      .order("step_number");
    if (!steps?.length) continue;
    const totalSteps = steps.length;

    // Find enrollments due: next_send_at <= now OR (step=0 AND next_send_at is null)
    const { data: due } = await sb
      .from("enrollments")
      .select("id,email,name,company,current_step,thread_message_id,next_send_at")
      .eq("sequence_id", seq.id)
      .eq("status", "active")
      .or(`next_send_at.lte.${now},next_send_at.is.null`);

    for (const enr of due || []) {
      try {
        const nextStepNum = (enr.current_step ?? 0) + 1;
        const step = steps.find((s) => s.step_number === nextStepNum);
        if (!step) continue;

        const inReplyTo = seq.same_thread && enr.current_step > 0 ? enr.thread_message_id || "" : "";
        const msgId = await sendBrevo(
          brevoKey,
          { email: fromEmail, name: fromName },
          { email: enr.email, name: enr.name || "" },
          step.subject,
          step.body || "",
          inReplyTo,
        );

        const isLast = nextStepNum >= totalSteps;
        const intervalMinutes = bellMinutes(minM, maxM);
        const nextSendAt = new Date(Date.now() + intervalMinutes * 60_000).toISOString();

        // Log the send
        await sb.from("send_log").insert({
          enrollment_id: enr.id,
          step_id: step.id,
          step_number: nextStepNum,
          brevo_message_id: msgId,
          status: "sent",
        });

        // Update enrollment
        const update: Record<string, unknown> = {
          current_step: nextStepNum,
          last_sent_at: now,
          status: isLast ? "completed" : "active",
          next_send_at: isLast ? null : nextSendAt,
        };
        if (seq.same_thread && nextStepNum === 1 && msgId) update.thread_message_id = msgId;
        await sb.from("enrollments").update(update).eq("id", enr.id);

        results.push(`✓ ${enr.email} step ${nextStepNum} — next in ${intervalMinutes}m`);
      } catch (err) {
        results.push(`✗ ${enr.email}: ${err.message}`);
      }
    }
  }

  return new Response(JSON.stringify({ sent: results.length, results }), {
    headers: { "Content-Type": "application/json" },
  });
});
