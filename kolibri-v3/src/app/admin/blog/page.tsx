'use client';

import { useEffect, useMemo, useState } from 'react';
import { Loader2, Plus, Save, Trash2, Eye, EyeOff, ExternalLink, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { BlogContent } from '@/components/blog/BlogContent';
import { slugify } from '@/lib/blog';

interface BlogPost {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  content: string;
  coverImage: string | null;
  tags: string;
  status: 'draft' | 'published';
  publishedAt: string | null;
  seoTitle: string | null;
  seoDescription: string | null;
  updatedAt: string;
}

interface PostForm {
  id?: string;
  title: string;
  slug: string;
  excerpt: string;
  content: string;
  coverImage: string;
  tags: string;
  status: 'draft' | 'published';
  seoTitle: string;
  seoDescription: string;
}

const emptyForm: PostForm = {
  title: '',
  slug: '',
  excerpt: '',
  content: '',
  coverImage: '',
  tags: '',
  status: 'draft',
  seoTitle: '',
  seoDescription: '',
};

function toForm(post: BlogPost): PostForm {
  return {
    id: post.id,
    title: post.title,
    slug: post.slug,
    excerpt: post.excerpt,
    content: post.content,
    coverImage: post.coverImage || '',
    tags: post.tags,
    status: post.status,
    seoTitle: post.seoTitle || '',
    seoDescription: post.seoDescription || '',
  };
}

export default function AdminBlogPage() {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [form, setForm] = useState<PostForm>(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [aiTopic, setAiTopic] = useState('');
  const [aiAudience, setAiAudience] = useState('');
  const [aiInstructions, setAiInstructions] = useState('');
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [subscribers, setSubscribers] = useState<{ id: string; email: string; status: string; createdAt: string }[]>([]);
  const [subscribersOpen, setSubscribersOpen] = useState(false);

  const loadPosts = async () => {
    try {
      const res = await fetch('/api/blog?all=1', { cache: 'no-store' });
      if (!res.ok) throw new Error('Не удалось загрузить статьи');
      const data = await res.json();
      setPosts(data.posts || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  };

  const loadSubscribers = async () => {
    try {
      const res = await fetch('/api/blog/subscribers', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      setSubscribers(data.subscribers || []);
    } catch {
      // не блокируем редактор из-за счётчика
    }
  };

  useEffect(() => { void loadPosts(); void loadSubscribers(); }, []);

  const update = <K extends keyof PostForm>(key: K, value: PostForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError('');
  };

  const startNew = () => {
    setForm(emptyForm);
    setAiTopic('');
    setAiAudience('');
    setAiInstructions('');
    setPreview(false);
    setDeleteConfirm(false);
    setError('');
  };

  const save = async (status: 'draft' | 'published') => {
    if (!form.title.trim()) {
      setError('Укажите заголовок');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const payload = { ...form, status, slug: form.slug || slugify(form.title) };
      const res = await fetch(form.id ? `/api/blog/${form.id}` : '/api/blog', {
        method: form.id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось сохранить');
      toast.success(status === 'published' ? 'Статья опубликована' : 'Черновик сохранён');
      setForm(toForm(data.post));
      await loadPosts();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Ошибка сохранения';
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const generateDraft = async () => {
    const topic = aiTopic.trim() || form.title.trim();
    if (topic.length < 3) {
      setError('Укажите тему или заголовок для генерации');
      return;
    }
    if ((form.title.trim() || form.excerpt.trim() || form.content.trim()) &&
      !window.confirm('ИИ заменит заголовок, описание, текст, теги и SEO-поля в текущей форме. Продолжить?')) {
      return;
    }

    setGenerating(true);
    setError('');
    try {
      const res = await fetch('/api/admin/blog/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, audience: aiAudience, instructions: aiInstructions }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Не удалось сгенерировать статью');
      setForm((current) => ({
        ...current,
        title: data.draft.title,
        slug: current.id ? current.slug : slugify(data.draft.title),
        excerpt: data.draft.excerpt,
        content: data.draft.content,
        tags: data.draft.tags.join(', '),
        status: 'draft',
        seoTitle: data.draft.seoTitle,
        seoDescription: data.draft.seoDescription,
      }));
      setPreview(false);
      if (data.fallback) {
        toast.warning('ИИ-провайдер временно недоступен: создан безопасный шаблон-черновик. Заполните и проверьте текст перед публикацией.');
      } else {
        toast.success('Черновик подготовлен. Проверьте факты перед сохранением.');
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Ошибка генерации';
      setError(message);
      toast.error(message);
    } finally {
      setGenerating(false);
    }
  };

  const remove = async () => {
    if (!form.id) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/blog/${form.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Не удалось удалить статью');
      toast.success('Статья удалена');
      startNew();
      await loadPosts();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Ошибка удаления');
    } finally {
      setSaving(false);
    }
  };

  const selected = useMemo(() => posts.find((p) => p.id === form.id), [posts, form.id]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    );
  }

  return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-emerald-400">Контент</p>
          <h1 className="mt-2 text-3xl font-semibold text-foreground">Блог</h1>
          <p className="mt-2 text-sm text-muted-foreground">Черновики, публикация, SEO и RSS — как в Ghost, только внутри «Коли».</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setSubscribersOpen((v) => !v)} aria-label="Подписчики блога" className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition hover:text-foreground">
            Подписчики: {subscribers.length}
          </button>
          <a href="/blog" target="_blank" rel="noreferrer" aria-label="Открыть публичный блог" className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition hover:text-foreground">
            <ExternalLink className="h-4 w-4" /> Открыть блог
          </a>
          <button onClick={startNew} aria-label="Новая статья" className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-foreground transition hover:bg-emerald-400">
            <Plus className="h-4 w-4" /> Новая статья
          </button>
        </div>
      </div>

      {subscribersOpen && (
        <div className="mt-4 rounded-2xl border border-border bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">Подписчики блога</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Хранятся в BlogSubscriber. Email-рассылка пока не подключена.</p>
            </div>
            <a href="/api/blog/subscribers?format=csv" className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground">Скачать CSV</a>
          </div>
          {subscribers.length === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground">Пока нет подписчиков. Форма есть внизу каждой статьи и в блоге.</p>
          ) : (
            <ul className="mt-3 max-h-56 divide-y divide-border overflow-auto">
              {subscribers.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                  <span className="truncate text-foreground">{s.email}</span>
                  <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">{s.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-2">
          {posts.length === 0 && <p className="rounded-xl border border-border p-4 text-sm text-muted-foreground">Пока нет статей.</p>}
          {posts.map((post) => (
            <button
              key={post.id}
              onClick={() => { setForm(toForm(post)); setAiTopic(post.title); setPreview(false); setDeleteConfirm(false); setError(''); }}
              aria-label={`Открыть статью: ${post.title}`}
              className={`w-full rounded-xl border p-3 text-left transition ${
                form.id === post.id ? 'border-emerald-400/40 bg-emerald-400/5' : 'border-border bg-card hover:bg-secondary/50'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 rounded-full ${post.status === 'published' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  {post.status === 'published' ? 'Опубликовано' : 'Черновик'}
                </span>
              </div>
              <p className="mt-2 line-clamp-2 text-sm font-medium text-foreground">{post.title}</p>
              <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">/{post.slug}</p>
            </button>
          ))}
        </aside>

        <section className="min-w-0 rounded-2xl border border-border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
            <div>
              <p className="text-sm font-medium text-foreground">{form.id ? 'Редактирование' : 'Новая статья'}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {selected ? `Обновлено ${new Date(selected.updatedAt).toLocaleString('ru-RU')}` : 'Заполните заголовок и текст'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setPreview((v) => !v)} aria-label={preview ? "Редактор" : "Превью"} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground">
                {preview ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                {preview ? 'Редактор' : 'Превью'}
              </button>
              <button onClick={() => save('draft')} disabled={saving} aria-label="Сохранить как черновик" className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50">
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                Черновик
              </button>
              <button onClick={() => save('published')} disabled={saving} aria-label="Опубликовать статью" className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-medium text-foreground hover:bg-emerald-400 disabled:opacity-50">
                Опубликовать
              </button>
              {form.id && (
                deleteConfirm ? (
                  <span className="inline-flex items-center gap-1 rounded-lg border border-red-500/30 px-2 py-1 text-xs text-red-400">
                    Удалить?
                    <button onClick={remove} className="rounded bg-red-500 px-2 py-1 text-foreground">Да</button>
                    <button onClick={() => setDeleteConfirm(false)} className="px-1 text-muted-foreground">Нет</button>
                  </span>
                ) : (
                  <button onClick={() => setDeleteConfirm(true)} aria-label="Удалить статью" className="inline-flex items-center gap-2 rounded-lg border border-red-500/20 px-3 py-2 text-xs text-red-400 hover:bg-red-500/10">
                    <Trash2 className="h-3.5 w-3.5" /> Удалить
                  </button>
                )
              )}
            </div>
          </div>

          {error && <div className="mx-5 mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>}

          {preview ? (
            <div className="p-5">
              <h2 className="font-serif text-4xl font-medium text-foreground">{form.title || 'Без заголовка'}</h2>
              {form.excerpt && <p className="mt-3 text-muted-foreground">{form.excerpt}</p>}
              <div className="mt-6 border-t border-border pt-6">
                {form.content.trim() ? <BlogContent content={form.content} /> : <p className="text-sm text-muted-foreground">Добавьте текст статьи в Markdown.</p>}
              </div>
            </div>
          ) : (
            <div className="space-y-5 p-5">
              <div className="space-y-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                <div>
                  <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <Sparkles className="h-4 w-4 text-emerald-400" /> Черновик с помощью ИИ
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Тема отправится в GigaChat. Ответ появится в редакторе и не будет сохранён или опубликован автоматически.
                  </p>
                </div>
                <input
                  value={aiTopic}
                  onChange={(e) => setAiTopic(e.target.value)}
                  maxLength={250}
                  placeholder="Тема статьи (или используйте заголовок ниже)"
                  aria-label="Тема статьи для ИИ"
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-emerald-400/50"
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <input
                    value={aiAudience}
                    onChange={(e) => setAiAudience(e.target.value)}
                    maxLength={120}
                    placeholder="Для кого статья (необязательно)"
                    aria-label="Аудитория статьи для ИИ"
                    className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-emerald-400/50"
                  />
                  <input
                    value={aiInstructions}
                    onChange={(e) => setAiInstructions(e.target.value)}
                    maxLength={1500}
                    placeholder="Пожелания к статье (необязательно)"
                    aria-label="Пожелания к статье для ИИ"
                    className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-emerald-400/50"
                  />
                </div>
                <button
                  type="button"
                  onClick={generateDraft}
                  disabled={generating || saving}
                  className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/30 px-3 py-2 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/10 disabled:opacity-50"
                >
                  {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  {generating ? 'Генерирую…' : 'Сгенерировать черновик'}
                </button>
                <p className="text-[11px] text-muted-foreground">
                  Сгенерированный текст может содержать ошибки — проверьте его и отдельно сохраните как черновик.
                </p>
              </div>
              <input
                value={form.title}
                onChange={(e) => update('title', e.target.value)}
                placeholder="Заголовок статьи"
                className="w-full border-0 bg-transparent font-serif text-4xl font-medium text-foreground outline-none placeholder:text-muted-foreground/40"
              />

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5">
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Slug</span>
                  <div className="flex gap-2">
                    <input value={form.slug} onChange={(e) => update('slug', e.target.value)} placeholder="statya-o-smetah" className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs text-foreground outline-none focus:border-emerald-400/50" />
                    <button onClick={() => update('slug', slugify(form.title))} className="shrink-0 rounded-lg border border-border px-2 text-[10px] text-muted-foreground hover:text-foreground">из заголовка</button>
                  </div>
                </label>
                <label className="space-y-1.5">
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Теги (через запятую)</span>
                  <input value={form.tags} onChange={(e) => update('tags', e.target.value)} placeholder="сметы, документы" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-emerald-400/50" />
                </label>
              </div>

              <label className="block space-y-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Краткое описание</span>
                <textarea value={form.excerpt} onChange={(e) => update('excerpt', e.target.value)} rows={2} maxLength={300} placeholder="О чём статья — 1–2 предложения" className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-emerald-400/50" />
                <span className="text-[10px] text-muted-foreground">{form.excerpt.length}/300</span>
              </label>

              <label className="block space-y-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Обложка (URL)</span>
                <input value={form.coverImage} onChange={(e) => update('coverImage', e.target.value)} placeholder="https://..." className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-emerald-400/50" />
              </label>

              <label className="block space-y-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Текст статьи (Markdown)</span>
                <textarea value={form.content} onChange={(e) => update('content', e.target.value)} rows={18} placeholder="Текст статьи в Markdown..." className="w-full resize-y rounded-lg border border-border bg-background px-3 py-3 font-mono text-[13px] leading-relaxed text-foreground outline-none focus:border-emerald-400/50" />
              </label>

              <details className="rounded-lg border border-border p-3">
                <summary className="cursor-pointer text-xs text-muted-foreground">SEO</summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <input value={form.seoTitle} onChange={(e) => update('seoTitle', e.target.value)} placeholder="SEO title" className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none" />
                  <input value={form.seoDescription} onChange={(e) => update('seoDescription', e.target.value)} placeholder="SEO description" className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none" />
                </div>
              </details>

              <p className="text-[11px] text-muted-foreground">
                Режим: {form.status === 'published' ? 'опубликовано' : 'черновик'}. Публикация доступна только администратору.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
