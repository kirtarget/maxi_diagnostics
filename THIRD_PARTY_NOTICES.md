# Third-party notices

This repository is distributed under the MIT License in `LICENSE`. It depends
on separately licensed open-source packages locked in `requirements-lock.txt`,
`requirements-dev-lock.txt`, and `miniapp/package-lock.json`. Their copyright
and license terms remain with their respective authors.

The Mini App build generates a production license bundle from the exact
installed dependency graph. It retains every packaged LICENSE, COPYING, and
NOTICE file, Next.js' vendored compiled-dependency notices, and the audited
libvips package README containing its licensing, bundled-library, source, and
rebuild information. The complete direct Next.js 16.3.0, React 19.2.6, and
React DOM 19.2.6 license texts are also retained under
`third_party_licenses/node/`. The generated bundle is copied into the
standalone runtime image.

The backend build likewise generates a fail-closed license bundle from every
installed Python distribution. Exact-version audited fallbacks for packages
that omit a license file are retained under `third_party_licenses/python/`;
pycairo's selected LGPL 2.1 text comes from the pinned Debian build image. The
runtime image also contains the Debian copyright/source notices for its
installed system packages, including Cairo and its font/image dependencies.

The bundled Liberation Sans font files under
`backend/diagnostic/assets/fonts/` are distributed under the SIL Open Font
License 1.1. The complete font license is included beside them as
`LICENSE_LIBERATION`.

Container builds use pinned official Python and Node.js images, and deployment
pulls a pinned official PostgreSQL image. Nginx is installed and maintained as
a host operating-system package; there is no Nginx container in this project.
Operators conveying container images must retain the generated bundles and the
licenses/notices supplied by the base images and installed packages. In
particular, the Alpine Mini App image includes the LGPL-licensed libvips binary
identified in `@img/sharp-libvips-linuxmusl-x64@1.3.2`; its captured README
provides the durable upstream source and rebuild references needed for the
applicable redistribution obligations. Obtain legal review for the intended
distribution model when images are conveyed outside the operating school.
