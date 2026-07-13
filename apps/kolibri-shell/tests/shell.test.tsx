import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../src/app/App';
import { FakeKolibriClient } from '../src/test/FakeKolibriClient';

describe('Morphing Conversation Shell', () => {
  it('keeps exactly one mascot in the DOM and morphs the menu into history', async () => {
    const user = userEvent.setup();
    render(<App client={new FakeKolibriClient()} />);
    await screen.findByPlaceholderText('Скажите, что нужно сделать...');

    expect(screen.getAllByTestId('kolibri-mascot')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Открыть историю' }));
    expect(screen.getByRole('dialog', { name: 'История проектов' })).toBeVisible();
    expect(screen.getByRole('dialog', { name: 'История проектов' })).toHaveAttribute('data-presentation', 'drawer');
    expect(screen.getAllByTestId('kolibri-mascot')).toHaveLength(1);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'История проектов' })).not.toBeInTheDocument();
  });

  it('streams a response, work trace and only a bound artifact into the current conversation', async () => {
    const user = userEvent.setup();
    render(<App client={new FakeKolibriClient()} />);
    const composer = await screen.findByRole('textbox', { name: 'Сообщение' });
    await user.type(composer, 'Составь документ');
    await user.click(screen.getByRole('button', { name: 'Отправить' }));

    expect(await screen.findByText('Составь документ')).toBeVisible();
    expect(await screen.findByText('Готовый ответ Kolibri.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Показать ход работы' })).toBeVisible();
    expect(screen.getByTestId('verified-artifact')).toHaveTextContent('Результат.pdf');
    expect(screen.getByRole('link', { name: 'Скачать Результат.pdf' })).toHaveAttribute(
      'href',
      '/v1/artifacts/artifact-1/content',
    );

    await user.click(screen.getByRole('button', { name: 'Показать ход работы' }));
    expect(screen.getAllByText('Составляю план')).toHaveLength(2);
  });

  it('hides unavailable tools and passes only a selected healthy tool', async () => {
    const user = userEvent.setup();
    const client = new FakeKolibriClient({
      projects: [],
      capabilities: [
        { id: 'web_search', name: 'Интернет', status: 'available', invocable: true },
        { id: 'project_knowledge', name: 'Проект', status: 'degraded', invocable: true },
        { id: 'image_generation', name: 'Изображения', status: 'unavailable', invocable: false },
      ],
    });
    render(<App client={client} />);
    await screen.findByPlaceholderText('Скажите, что нужно сделать...');

    await user.click(screen.getByRole('button', { name: 'Инструменты' }));
    const menu = screen.getByRole('menu', { name: 'Доступные инструменты' });
    expect(within(menu).getByText('Интернет')).toBeVisible();
    expect(within(menu).getByText('Проект')).toBeVisible();
    expect(within(menu).queryByText('Изображения')).not.toBeInTheDocument();
    await user.click(within(menu).getByRole('menuitemcheckbox', { name: /Интернет/ }));
    await user.type(screen.getByRole('textbox', { name: 'Сообщение' }), 'Новости');
    await user.click(screen.getByRole('button', { name: 'Отправить' }));

    await waitFor(() => expect(client.requests).toHaveLength(1));
    expect(client.requests[0]?.tools).toEqual(['web_search']);
  });

  it('stops an active streamed response with the visible stop control', async () => {
    const user = userEvent.setup();
    const client = new FakeKolibriClient({ projects: [], capabilities: [] }, true);
    render(<App client={client} />);
    await user.type(await screen.findByRole('textbox', { name: 'Сообщение' }), 'Долгая задача');
    await user.click(screen.getByRole('button', { name: 'Отправить' }));
    await user.click(await screen.findByRole('button', { name: 'Остановить' }));

    expect(await screen.findByText('Ответ остановлен.')).toBeVisible();
    expect(client.cancelled).toContain('response-1');
  });
});
