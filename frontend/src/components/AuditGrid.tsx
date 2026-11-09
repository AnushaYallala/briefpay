"use client";
/** The AI audit trail as an AG Grid (Community only). Logic lives in `lib/audit.ts`; this is the thin view. */
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import { Badge } from "@/components/ui";
import { agentLabel, latencyText, shortHash, statusInfo } from "@/lib/audit";
import { formatDateTime } from "@/lib/time";
import type { AgentRun } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

export function AuditGrid({ runs, quickFilter, onOpen }: { runs: AgentRun[]; quickFilter: string; onOpen: (run: AgentRun) => void }) {
  const columns = useMemo<ColDef<AgentRun>[]>(() => [
    { field: "id", headerName: "#", width: 80, pinned: "left", sort: "desc" },
    { field: "created_at", headerName: "Time", width: 150, valueFormatter: (p) => formatDateTime(p.value) },
    { field: "agent", headerName: "Agent", width: 210, valueFormatter: (p) => agentLabel(p.value), getQuickFilterText: (p) => agentLabel(p.value) },
    { colId: "model", headerName: "Model", width: 200, valueGetter: (p) => (p.data ? `${p.data.provider} / ${p.data.model}` : "") },
    { field: "prompt_version", headerName: "Prompt", width: 110 },
    { field: "latency_ms", headerName: "Time taken", width: 120, type: "rightAligned", valueFormatter: (p) => latencyText(p.value) },
    { colId: "tokens", headerName: "Tokens in / out", width: 140, type: "rightAligned", valueGetter: (p) => (p.data ? `${p.data.input_tokens ?? 0} / ${p.data.output_tokens ?? 0}` : "") },
    {
      field: "status", headerName: "Result", width: 220,
      getQuickFilterText: (p) => statusInfo(p.value).label,          // search finds the plain words (the raw code is found too)
      cellRenderer: (p: ICellRendererParams<AgentRun>) => <Badge tone={statusInfo(p.value).tone}>{statusInfo(p.value).label}</Badge>,
    },
    { field: "input_hash", headerName: "Input fingerprint", width: 150, cellRenderer: (p: ICellRendererParams<AgentRun>) => <span title={p.value} className="font-mono">{shortHash(p.value)}</span> },
    {
      colId: "details", headerName: "", width: 90, sortable: false, filter: false,
      cellRenderer: (p: ICellRendererParams<AgentRun>) => (p.data ? <button className="text-sea-700 underline" onClick={() => onOpen(p.data!)}>Details</button> : null),
    },
  ], [onOpen]);

  return (
    <div className={runs.length > 200 ? "h-[600px]" : ""} data-testid="audit-grid">
      <AgGridReact<AgentRun>
        theme={themeQuartz}
        rowData={runs}
        columnDefs={columns}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        quickFilterText={quickFilter}
        domLayout={runs.length > 200 ? "normal" : "autoHeight"}
        suppressColumnVirtualisation
        getRowId={(p) => String(p.data.id)}
        getRowClass={(p) => (p.data && (p.data.status === "ERROR" || p.data.status === "SCHEMA_INVALID") ? "bg-red-50" : undefined)}
        overlayNoRowsTemplate="No AI calls match"
      />
    </div>
  );
}
