"use client";
/** The requirements of a brief as an AG Grid (Community only). Logic lives in `lib/brd.ts`; this is the thin view. */
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import { Badge } from "@/components/ui";
import { namesOf, priorityTone } from "@/lib/brd";
import type { BrdRequirement } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

export function RequirementsGrid({ requirements, names, quickFilter, onOpen }: {
  requirements: BrdRequirement[]; names: Record<number, string>; quickFilter: string; onOpen: (r: BrdRequirement) => void;
}) {
  const columns = useMemo<ColDef<BrdRequirement>[]>(() => [
    { field: "code", headerName: "Code", width: 110, pinned: "left", sort: "asc" },
    { field: "title", headerName: "Requirement", width: 260 },
    { field: "priority", headerName: "Priority", width: 110, cellRenderer: (p: ICellRendererParams<BrdRequirement>) => <Badge tone={priorityTone(p.value)}>{p.value}</Badge> },
    { field: "weight", headerName: "Weight", width: 100, type: "rightAligned" },
    { colId: "askedBy", headerName: "Asked for by", width: 200, valueGetter: (p) => (p.data ? namesOf(names, p.data.requested_by) : "") },
    { colId: "checks", headerName: "Checks", width: 100, type: "rightAligned", valueGetter: (p) => p.data?.acceptance_criteria.length ?? 0 },
    { colId: "details", headerName: "", width: 100, sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<BrdRequirement>) => (p.data ? <button className="text-sea-700 underline" onClick={() => onOpen(p.data!)}>Details</button> : null) },
  ], [names, onOpen]);
  return (
    <div data-testid="requirements-grid">
      <AgGridReact<BrdRequirement>
        theme={themeQuartz}
        rowData={requirements}
        columnDefs={columns}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        quickFilterText={quickFilter}
        domLayout="autoHeight"
        suppressColumnVirtualisation
        getRowId={(p) => p.data.code}
        overlayNoRowsTemplate="No requirements match"
      />
    </div>
  );
}
