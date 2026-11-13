'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Check, AlertCircle, Info } from 'lucide-react';
import { toast } from 'sonner';
import { PLAN_CONFIG, type PlanType } from '@/lib/subscription';

interface SubscriptionInfo {
  plan: PlanType;
  status: string;
  currentPeriodEnd: string | null;
  priceMonthly: number;
  maxRequestsPerDay: number;
  features: string[];
}

export function BillingView() {
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);

  useEffect(() => {
    fetchSubscription();
  }, []);

  const fetchSubscription = async () => {
    try {
      const res = await fetch('/api/subscription');
      if (!res.ok) {
        if (res.status === 401) {
          toast.error('Не авторизованы. Перезайдите в аккаунт.');
          return;
        }
        if (res.status === 500) {
          toast.error('Сервер временно недоступен. Попробуйте позже.');
          return;
        }
        throw new Error('Failed to fetch subscription');
      }
      const data = await res.json();
      setSubscription(data.info);
    } catch (error) {
      console.error('Failed to fetch subscription:', error);
      toast.error('Не удалось загрузить информацию о подписке');
    } finally {
      setLoading(false);
    }
  };

  const handleUpgrade = async (plan: PlanType) => {
    setUpgrading(plan);
    try {
      const res = await fetch('/api/subscription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          toast.error('Не авторизованы. Перезайдите в аккаунт.');
          return;
        }
        if (res.status === 402) {
          toast.error('Требуется оплата. В демо-режиме это не проверяется.');
          return;
        }
        if (res.status === 500) {
          toast.error('Сервер временно недоступен. Попробуйте позже.');
          return;
        }
        const data = await res.json();
        throw new Error(data.error || 'Не удалось изменить тариф');
      }

      toast.success(plan === 'free' ? 'Бесплатный тариф активирован' : `Платёж для тарифа «${PLAN_CONFIG[plan].name}» ещё не подключён`);
      await fetchSubscription();
    } catch (error) {
      console.error('Failed to upgrade subscription:', error);
      toast.error((error as Error).message || 'Не удалось изменить тариф');
    } finally {
      setUpgrading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold text-foreground">Подписка и оплата</h1>
          <p className="text-sm text-muted-foreground mt-1">Управляйте тарифом и просмотрами</p>
        </div>

        {/* Demo mode banner */}
        <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5">
          <Info size={14} className="shrink-0 text-amber-400" />
          <p className="text-xs text-amber-300/90">
            Демо-режим: платёжный шлюз не подключён. Смена тарифа активирует функции, но деньги не списываются.
          </p>
        </div>

        {/* Current plan */}
        {subscription && (
          <div className="bg-card border border-border rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{PLAN_CONFIG[subscription.plan].name}</h2>
                {subscription.currentPeriodEnd && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Действует до {new Date(subscription.currentPeriodEnd).toLocaleDateString('ru-RU')}
                  </p>
                )}
              </div>
              {subscription.status === 'active' && (
                <span className="text-xs bg-emerald-500/20 text-emerald-400 px-3 py-1 rounded-full">
                  Активен
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-secondary/50 px-3 py-2">
                <p className="text-xs text-muted-foreground">Запросов в день</p>
                <p className="text-sm font-medium text-foreground mt-0.5">
                  {subscription.maxRequestsPerDay === -1 ? 'Безлимит' : subscription.maxRequestsPerDay}
                </p>
              </div>
              <div className="rounded-xl bg-secondary/50 px-3 py-2">
                <p className="text-xs text-muted-foreground">Стоимость</p>
                <p className="text-sm font-medium text-foreground mt-0.5">
                  {subscription.priceMonthly === 0 ? 'Бесплатно' : `${subscription.priceMonthly} ₽/мес`}
                </p>
              </div>
            </div>

            {subscription.features.length > 0 && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs text-muted-foreground mb-2">Включено:</p>
                <div className="grid grid-cols-2 gap-2">
                  {subscription.features.slice(0, 6).map((feature, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-foreground/70">
                      <Check size={12} className="text-emerald-400 mt-0.5 shrink-0" />
                      <span>{feature}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Available plans */}
        <div className="bg-card border border-border rounded-2xl p-5">
          <h3 className="text-sm font-medium text-foreground mb-4">Доступные тарифы</h3>
          <div className="space-y-3">
            {Object.entries(PLAN_CONFIG).map(([key, plan]) => {
              const isCurrent = subscription?.plan === key;
              const isUpgrading = upgrading === key;

              return (
                <div
                  key={key}
                  className={`p-4 rounded-xl border transition-all ${
                    isCurrent
                      ? 'border-cyan-400/30 bg-cyan-400/5'
                      : 'border-border bg-secondary/30 hover:bg-secondary/50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h4 className="text-sm font-medium text-foreground">{plan.name}</h4>
                      <p className="text-xs text-muted-foreground">{plan.subtitle}</p>
                    </div>
                    {isCurrent && (
                      <span className="text-[10px] bg-cyan-400/20 text-cyan-400 px-2 py-0.5 rounded-full">
                        Текущий
                      </span>
                    )}
                  </div>

                  <div className="flex items-baseline gap-1 mb-3">
                    <span className="text-lg font-semibold text-foreground">
                      {plan.priceMonthly === 0 ? 'Бесплатно' : plan.priceMonthly.toLocaleString('ru-RU')}
                    </span>
                    {plan.priceMonthly > 0 && <span className="text-xs text-muted-foreground">/мес</span>}
                  </div>

                  {!isCurrent && (
                    <button
                      onClick={() => handleUpgrade(key as PlanType)}
                      disabled={isUpgrading}
                      className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary text-primary-foreground px-3 py-2 text-xs font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                    >
                      {isUpgrading ? (
                        <>
                          <Loader2 size={12} className="animate-spin" />
                          Обновление...
                        </>
                      ) : (
                        <>
                          Выбрать
                          <span className="rounded-full bg-primary-foreground/20 px-1.5 py-0.5 text-[9px] font-medium">
                            Демо
                          </span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Chat hint */}
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground pt-4">
          <Info className="h-3.5 w-3.5 shrink-0" />
          <span>Также вы можете управлять подпиской через чат — напишите "подписка" или "тариф"</span>
        </div>
      </div>
    </div>
  );
}
