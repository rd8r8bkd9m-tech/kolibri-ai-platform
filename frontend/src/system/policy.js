
export function hasCapability(role, capability) { return role?.grants?.includes('*') || role?.grants?.includes(capability); }
export function resolveIntent(manifest, text='', roleId='client') {
  const value = String(text || '').toLowerCase();
  const role = manifest.roles[roleId] || manifest.roles.client;
  const intents = Object.values(manifest.intents).sort((a,b)=>(Number(b.priority)||0)-(Number(a.priority)||0));
  return intents.find((intent)=>intent.triggers.some((trigger)=>value.includes(String(trigger).toLowerCase()))) || manifest.intents[role.default_intent] || manifest.intents.estimate_start;
}
export function resolveTurn(manifest, { roleId='client', text='', deviceId='auto' }) {
  const role = manifest.roles[roleId] || manifest.roles.client;
  const plan = manifest.plans[role.plan] || { id: role.plan, label: role.plan };
  const device = manifest.devices[deviceId] || manifest.devices.auto;
  const intent = resolveIntent(manifest, text, role.id);
  const matches = Object.values(manifest.components).filter(c => c.intents.includes(intent.id) || c.intents.includes('*'));
  const components = matches.filter(c => c.required.every(cap => hasCapability(role, cap)));
  const hidden = matches.filter(c => !c.required.every(cap => hasCapability(role, cap)));
  const denied = [...new Set(hidden.flatMap(c => c.required.filter(cap => !hasCapability(role, cap))))].map(id => ({ id, ...(manifest.capabilities[id] || {}) }));
  const assistant = hidden.length && !components.length ? 'Эта функция недоступна для вашей роли или тарифа. Закрытые окна не отрисованы.' : intent.assistant;
  return { role, plan, device, intent, components, hidden, denied_capabilities: denied, assistant };
}
