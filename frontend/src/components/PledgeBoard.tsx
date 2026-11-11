"use client";
/** The pledge board as an AG Grid (Community only): who has pledged and what became of each pledge. Logic lives in `lib/campaign.ts`. */
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Badge } from "@/components/ui";
import { BOARD_STATUS, type BoardRow } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { formatDateTime } from "@/lib/time";

ModuleRegistry.registerModules([AllCommunityModule]);

const COLUMNS = (currency: string): ColDef<BoardRow>[] => [
  { field: "name", headerName: "Supporter", minWidth: 160, flex: 1.4 },
  {
    field: "status", headerName: "Status", minWidth: 130, flex: 1,
    cellRenderer: (p: ICellRendererParams<BoardRow>) => <Badge tone={(BOARD_STATUS[p.value] ?? { tone: "grey" }).tone}>{(BOARD_STATUS[p.value] ?? { label: p.value }).label}</Badge>,
  },
  { field: "amount_cents", headerName: "Collected", minWidth: 120, flex: 1, type: "rightAligned", valueFormatter: (p) => (p.value === null ? "held" : formatMoney(p.value, currency)) },
  { field: "at", headerName: "Updated", minWidth: 155, flex: 1.2, valueFormatter: (p) => formatDateTime(p.value) },
];

export function PledgeBoard({ rows, currency }: { rows: BoardRow[]; currency: string }) {
  return (
    <div data-testid="pledge-board" className="overflow-hidden rounded-xl border border-slate-200/80">
      <AgGridReact<BoardRow>
        theme={themeQuartz}
        rowData={rows}
        columnDefs={COLUMNS(currency)}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        domLayout="autoHeight"
        suppressColumnVirtualisation
        getRowId={(p) => p.data.pledge}
        overlayNoRowsTemplate="No pledges yet"
      />
    </div>
  );
}
