// Timeline band geometry now lives in the shared `@/lib/timeline/geometry`
// module so the rate-workbench timeline can reuse it. Re-exported here to keep
// availability's existing imports (and `geometry.test.ts`) stable.
export {
  bandEdges,
  bandGeometry,
  assignLanes,
  type BandEdges,
  type BandGeometry,
} from "@/lib/timeline/geometry";
