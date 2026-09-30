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
