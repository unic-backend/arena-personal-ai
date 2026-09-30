# Third-party notices

## Agnes Video Generator

ARENA's Agnes provider interoperates with the public REST API of **Agnes Video Generator**.

- Upstream: https://github.com/lcy362/agnes-video-generator
- Copyright: upstream contributors
- License: MIT

The current ARENA integration is an independently implemented API adapter and does not vendor the upstream source tree. The upstream project and license remain the authoritative references for Agnes Video Generator itself.

## CodeFormer image restoration (optional external engine)

ARENA can invoke an operator-installed checkout of **CodeFormer** through its
official command-line interface. No CodeFormer source code or model weight is
vendored in this repository.

- Upstream: https://github.com/sczhou/CodeFormer
- Pinned integration revision: `b33cc7d639d6545bfcccc7e0bc6ae51f24e79c2b`
- Copyright: 2022 S-Lab
- License: NTU S-Lab License 1.0 (`licenses/CodeFormer-LICENSE.txt`;
  non-commercial use under its conditions; commercial use requires contacting
  the contributors)
- Official model release: https://github.com/sczhou/CodeFormer/releases/tag/v0.1.0

The external checkout also contains/uses BasicSR (Apache-2.0), FaceXLib
(MIT), Real-ESRGAN (BSD-3-Clause), and face detection components. Their
license files in the operator-installed upstream checkout are authoritative.
ARENA's installer preserves that checkout and its notices rather than copying
those projects into this repository.

## Edit-Banana editable diagram conversion (optional external engine)

ARENA can invoke an operator-installed checkout of **Edit-Banana** through its
command-line interface in an isolated subprocess. No Edit-Banana source code,
libraries, or model weights are vendored or copied into this repository.

- Upstream: https://github.com/BIT-DataLab/Edit-Banana
- Pinned integration revision: `88c6e288ef8329606114eb91924559c5d1838d2e`
- Copyright: BIT-DataLab / Beijing Institute of Technology contributors
- License: GNU Affero General Public License v3.0 (GNU AGPL-3.0 in the upstream `LICENSE` file; note that the upstream README describes the project as Apache-2.0, but the authoritative `LICENSE` file is AGPL-3.0).
- External engine isolation: Edit-Banana operates in a separate external Python environment outside of ARENA's repository.
- Segment Anything Model 3 (SAM3): SAM3 is an external dependency of Edit-Banana subject to its own Meta/SAM3 license and gated checkpoint access requirements. No SAM3 weights are bundled or distributed.

## Codebase-Memory MCP (optional external engine)

ARENA interoperates with **Codebase-Memory MCP** over its standard Model Context Protocol (MCP) stdio interface. No Codebase-Memory MCP source code or binaries are vendored or copied into this repository.

- Upstream: https://github.com/DeusData/codebase-memory-mcp
- Research preprint: *Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP* (arXiv:2603.27277)
- Copyright: (c) 2025-2026 DeusData contributors
- License: MIT License
- External engine isolation: Codebase-Memory runs as an isolated local subprocess communicating over JSON-RPC 2.0 stdio with SQLite persistence. All data exchanges are subject to ARENA's security boundary and untrusted data wrapping.
