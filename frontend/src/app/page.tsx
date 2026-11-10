"use client";
import { ProjectCardView } from "@/components/ProjectCard";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import type { ProjectCard } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Home() {
  const { data, error, loading, slow, reload } = useApi<{ projects: ProjectCard[] }>("/projects");
  return (
    <div>
      <section className="mb-6">
        <h1 className="text-2xl font-bold">Pledge together. Pay only if we get there.</h1>
        <p className="mt-1 max-w-2xl text-gray-700">
          Neighbours pool money for one shared project. A pledge is only a hold: nobody is charged unless the goal is reached, and the builder is paid only after the work is checked.
        </p>
      </section>
      {loading && <Loading what="Loading projects" slow={slow} />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {!loading && !error && data && data.projects.length === 0 && (
        <Empty title="No projects yet">Ask the demo administrator to load the demo data, or start a project.</Empty>
      )}
      {!loading && !error && data && data.projects.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2">{data.projects.map((p) => <ProjectCardView key={p.id} p={p} />)}</ul>
      )}
    </div>
  );
}
