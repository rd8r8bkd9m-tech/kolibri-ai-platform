import type { TaskRow } from "../api/types";

export function TaskTable({ tasks }: { tasks: TaskRow[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Задача</th>
          <th>Приоритет</th>
          <th>Статус</th>
          <th>Создана</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((task) => (
          <tr key={task.id}>
            <td>{task.title}</td>
            <td>{task.priority}</td>
            <td>{task.status}</td>
            <td>{task.created_at}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
