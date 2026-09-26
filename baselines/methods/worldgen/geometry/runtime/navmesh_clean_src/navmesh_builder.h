#pragma once

#include <vector>
#include <cstdint>

// forward declare Detour type
struct dtNavMesh;

// Build function:
// - vertices: Flat float list: x0,y0,z0, x1,y1,z1, ...
// - indices:  Flat int list of triangle indices: 0,1,2, 3,4,5, ...
// - outVerts: Optional; if non-null, populated with flat polymesh vertices on success (x,y,z,...)
// - outTris:  Optional; if non-null, populated with flat triangle indices into outVerts on success (i0,i1,i2,...)
// Returns a non-null dtNavMesh* on success; the caller must free it.
//       Returns nullptr on failure.
// The function attempts to copy the Recast polymesh vertices and fan-triangulated polygons to
//       outVerts/outTris when their pointers are non-null, allowing Python to access the mesh
//       without relying on private dtNavMesh APIs.
dtNavMesh* buildDetourMeshFromTriangles(const std::vector<float>& vertices,
                                        const std::vector<int>& indices,
                                        float cellSize = 0.3f,
                                        float cellHeight = 0.2f,
                                        float agentHeight = 2.0f,
                                        float agentRadius = 0.6f,
                                        float agentMaxClimb = 0.9f,
                                        float maxSlope = 45.0f,
                                        std::vector<float>* outVerts = nullptr,
                                        std::vector<int>* outTris = nullptr);
void freeDetourMesh(dtNavMesh* mesh);