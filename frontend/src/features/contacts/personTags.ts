// The customer-tag taxonomy now lives in lib/domain (GAP-072) so the clients
// list can read it without an edge into contacts; re-exported here for the
// in-feature tag components.
export { PERSON_TAGS, type PersonTag } from "@/lib/domain/personTags";
