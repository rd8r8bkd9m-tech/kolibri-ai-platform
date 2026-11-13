/**
 * Subscription API endpoint.
 * GET — получить текущую подписку
 * POST — создать/изменить подписку
 * DELETE — отменить подписку
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { requireAuthOrRespond } from '@/lib/auth/middleware';
import {
  getUserSubscription,
  createSubscription,
  cancelSubscription,
  getSubscriptionInfo,
  type PlanType,
} from '@/lib/subscription';

const createSubscriptionSchema = z.object({
  plan: z.enum(['free', 'pro', 'business', 'enterprise']),
  providerPaymentId: z.string().optional(),
});

export async function GET(request: NextRequest) {
  // Проверка авторизации
  const authCheck = await requireAuthOrRespond(request, { requireAuth: true });
  if (authCheck.response) return authCheck.response;

  try {
    const subscription = await getUserSubscription(authCheck.context.userId!);
    const info = await getSubscriptionInfo(authCheck.context.userId!);

    return NextResponse.json({
      subscription,
      info,
    });
  } catch (error) {
    console.error('Failed to get subscription:', error);
    return NextResponse.json({ error: 'Failed to get subscription' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  // Проверка авторизации
  const authCheck = await requireAuthOrRespond(request, { requireAuth: true });
  if (authCheck.response) return authCheck.response;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Некорректный запрос' }, { status: 400 });
  }

  const parsed = createSubscriptionSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? 'Некорректные данные' },
      { status: 400 }
    );
  }

  const { plan, providerPaymentId } = parsed.data;

  // Paid plans must never be activated without a verified payment provider.
  // The demo UI is explicit, but the API also fails closed for direct callers.
  if (plan !== 'free' && !providerPaymentId) {
    return NextResponse.json(
      { error: 'Платёжный шлюз не подключён. Бесплатный тариф доступен без оплаты.' },
      { status: 402 },
    );
  }

  const result = await createSubscription(
    authCheck.context.userId!,
    plan as PlanType,
    providerPaymentId
  );

  if (!result.success) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }

  return NextResponse.json({ success: true, plan });
}

export async function DELETE(request: NextRequest) {
  // Проверка авторизации
  const authCheck = await requireAuthOrRespond(request, { requireAuth: true });
  if (authCheck.response) return authCheck.response;

  const result = await cancelSubscription(authCheck.context.userId!);

  if (!result.success) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
