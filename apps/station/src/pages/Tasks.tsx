import { useState } from "react";
import { TaskTable } from "../components/TaskTable";
import type { TaskRow } from "../api/types";

const EMPTY: TaskRow[] = [];

export function TasksPage() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  return (
    <section>
      <h2>Tasks</h2>
      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          alert(`Demo submit: ${title}`);
          setTitle("");
          setDescription("");
        }}
      >
        <label>
          Заголовок
          <br />
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label>
          Описание
          <br />
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <button type="submit">Создать задачу</button>
      </form>
      <TaskTable tasks={EMPTY} />
    </section>
  );
}
