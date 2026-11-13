const SVG_NS = "http://www.w3.org/2000/svg";
const MAN_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九"];
const HONORS = ["東", "南", "西", "北", "白", "發", "中"];

const PIN_LAYOUTS = {
  2: [[50, 38], [50, 92]],
  3: [[30, 30], [50, 65], [70, 100]],
  4: [[31, 36], [69, 36], [31, 94], [69, 94]],
  5: [[29, 30], [71, 30], [50, 65], [29, 100], [71, 100]],
  6: [[31, 27], [69, 27], [31, 65], [69, 65], [31, 103], [69, 103]],
  7: [[27, 27], [50, 27], [73, 27], [34, 65], [66, 65], [34, 101], [66, 101]],
  8: [[31, 21], [69, 21], [31, 50], [69, 50], [31, 80], [69, 80], [31, 109], [69, 109]],
  9: [[25, 25], [50, 25], [75, 25], [25, 65], [50, 65], [75, 65], [25, 105], [50, 105], [75, 105]],
};

const SOU_LAYOUTS = {
  2: [[50, 34], [50, 96]],
  3: [[50, 30], [30, 94], [70, 94]],
  4: [[34, 34], [66, 34], [34, 94], [66, 94]],
  5: [[30, 29], [70, 29], [50, 65], [30, 101], [70, 101]],
  6: [[31, 27], [69, 27], [31, 65], [69, 65], [31, 103], [69, 103]],
  7: [[50, 20], [27, 61], [50, 61], [73, 61], [27, 105], [50, 105], [73, 105]],
  8: [[31, 21], [69, 21], [31, 50], [69, 50], [31, 80], [69, 80], [31, 109], [69, 109]],
  9: [[25, 24], [50, 24], [75, 24], [25, 65], [50, 65], [75, 65], [25, 106], [50, 106], [75, 106]],
};

export function tileType(id) { return Math.floor(Number(id) / 4); }

export function tileSuit(id) {
  const type = tileType(id);
  return type < 9 ? "man" : type < 18 ? "pin" : type < 27 ? "sou" : "honor";
}

export function tileLabel(id) {
  const type = tileType(id);
  if (type < 9) return `${type + 1}萬`;
  if (type < 18) return `${type - 8}筒`;
  if (type < 27) return `${type - 17}索`;
  return HONORS[type - 27];
}

export function tileFaceSpec(type) {
  if (!Number.isInteger(type) || type < 0 || type > 33) throw new RangeError("mahjong tile type must be 0-33");
  if (type < 9) return {kind: "man", rank: type + 1, label: `${MAN_NUMERALS[type]}萬`};
  if (type < 18) {
    const rank = type - 8;
    return {kind: "pin", rank, label: `${rank}筒`, marks: rank === 1 ? [[50, 65]] : PIN_LAYOUTS[rank]};
  }
  if (type < 27) {
    const rank = type - 17;
    return {kind: "sou", rank, label: `${rank}索`, marks: rank === 1 ? [[50, 65]] : SOU_LAYOUTS[rank]};
  }
  return {kind: "honor", rank: type - 26, label: HONORS[type - 27]};
}

function svgNode(documentRef, name, attributes = {}, text = "") {
  const node = documentRef.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text) node.textContent = text;
  return node;
}

function drawPinOne(svg, documentRef) {
  const group = svgNode(documentRef, "g", {class: "pin-one", transform: "translate(50 65)"});
  group.append(svgNode(documentRef, "circle", {class: "pin-ring", r: 36}), svgNode(documentRef, "circle", {class: "pin-ring", r: 31}));
  for (let angle = 0; angle < 360; angle += 30) {
    group.append(svgNode(documentRef, "path", {class: "pin-flower", d: "M0 -13 C-11 -19 -7 -29 0 -29 C7 -29 11 -19 0 -13Z", transform: `rotate(${angle})`}));
  }
  group.append(svgNode(documentRef, "circle", {class: "pin-ring", r: 12}), svgNode(documentRef, "circle", {class: "pin-center", r: 7}));
  svg.append(group);
}

function drawPin(svg, documentRef, mark, index, rank) {
  const [x, y] = mark;
  const radius = rank === 2 ? 17 : rank <= 4 ? 14 : rank <= 6 ? 12 : 10.5;
  const red = (rank === 3 && index === 1) || (rank === 5 && index === 2) || (rank === 9 && index === 4);
  const group = svgNode(documentRef, "g", {class: `pin-dot${red ? " pin-red" : ""}`, transform: `translate(${x} ${y}) scale(${radius / 10})`});
  group.append(svgNode(documentRef, "circle", {class: "pin-ring", r: 10}));
  for (let angle = 0; angle < 360; angle += 60) {
    group.append(svgNode(documentRef, "ellipse", {class: "pin-flower", cx: 0, cy: -5.5, rx: 2.1, ry: 3.1, transform: `rotate(${angle})`}));
  }
  group.append(svgNode(documentRef, "circle", {class: "pin-center", r: 2}));
  svg.append(group);
}

function drawBird(svg, documentRef) {
  // Slender crane engraving: a single dark silhouette with cut feather strokes.
  const bird = svgNode(documentRef, "g", {class: "sou-bird"});
  bird.append(
    svgNode(documentRef, "path", {class: "crane-tail", d: "M44 74 Q31 101 18 116 Q42 109 52 82 M49 78 Q45 107 37 119 Q57 105 59 81"}),
    svgNode(documentRef, "path", {class: "crane-body", d: "M31 75 C27 60 36 49 50 49 C61 48 63 41 60 33 C56 21 62 12 70 15 C80 20 74 29 69 31 C73 43 76 55 66 65 C59 78 43 85 31 75Z"}),
    svgNode(documentRef, "path", {class: "crane-wing", d: "M31 68 Q38 50 57 53 Q59 72 37 79 Q43 71 46 63 Q39 70 31 68Z"}),
    svgNode(documentRef, "path", {class: "crane-feathers", d: "M37 66 Q43 56 52 57 M38 72 Q48 65 53 59 M42 75 Q55 67 57 59 M42 84 L28 106 M48 87 L41 108"}),
    svgNode(documentRef, "path", {class: "crane-crown", d: "M62 19 Q66 10 72 17 L72 21 Q67 18 62 22Z"}),
    svgNode(documentRef, "path", {class: "crane-beak", d: "M74 22 L89 26 L74 28Z"}),
    svgNode(documentRef, "circle", {class: "crane-eye", cx: 70, cy: 23, r: 1.5}),
    svgNode(documentRef, "path", {class: "crane-legs", d: "M58 75 L64 96 L55 101 M63 71 L71 91 L80 94 M20 104 Q49 98 81 105"}),
  );
  svg.append(bird);
}

function drawBamboo(svg, documentRef, mark, index, rank) {
  const [x, y] = mark;
  const red = (rank === 5 && index === 2) || (rank === 7 && index === 0) || (rank === 9 && index === 4);
  const angle = rank === 8 ? (index % 2 === 0 ? -22 : 22) : 0;
  const scale = rank <= 3 ? 1.3 : rank === 8 ? .8 : 1;
  const group = svgNode(documentRef, "g", {class: `bamboo-stick${red ? " bamboo-red" : ""}`, transform: `translate(${x} ${y}) rotate(${angle}) scale(${scale})`});
  group.append(
    svgNode(documentRef, "path", {class: "bamboo-stem", d: "M-4 -16 Q0 -13 4 -16 L3 -3 L4 0 L3 3 L4 16 Q0 13 -4 16 L-3 3 L-4 0 L-3 -3Z"}),
    svgNode(documentRef, "path", {class: "bamboo-joints", d: "M-6 -16 Q0 -13 6 -16 M-5 0 Q0 2 5 0 M-6 16 Q0 13 6 16"}),
    svgNode(documentRef, "path", {class: "bamboo-cut", d: "M-1 -11 L-1 -4 M-1 5 L-1 11"}),
  );
  svg.append(group);
}

export function createTileFace(id, documentRef = document) {
  const spec = tileFaceSpec(tileType(id));
  const svg = svgNode(documentRef, "svg", {
    class: `tile-face ${spec.kind}-face`,
    viewBox: "0 0 100 130",
    width: 100, height: 130,
    preserveAspectRatio: "xMidYMid meet",
    "aria-hidden": "true",
    focusable: "false",
    "data-kind": spec.kind,
    "data-rank": spec.rank,
  });

  if (spec.kind === "man") {
    svg.append(
      svgNode(documentRef, "text", {class: "mahjong-glyph man-number", x: 50, y: 67, "text-anchor": "middle"}, MAN_NUMERALS[spec.rank - 1]),
      svgNode(documentRef, "text", {class: "mahjong-glyph man-suit", x: 50, y: 108, "text-anchor": "middle"}, "萬"),
    );
  } else if (spec.kind === "pin") {
    if (spec.rank === 1) drawPinOne(svg, documentRef);
    else spec.marks.forEach((mark, index) => drawPin(svg, documentRef, mark, index, spec.rank));
  } else if (spec.kind === "sou") {
    if (spec.rank === 1) drawBird(svg, documentRef);
    else spec.marks.forEach((mark, index) => drawBamboo(svg, documentRef, mark, index, spec.rank));
  } else if (spec.label === "白") {
    svg.append(
      svgNode(documentRef, "rect", {class: "white-dragon-frame", x: 21, y: 27, width: 58, height: 76, rx: 8}),
      svgNode(documentRef, "rect", {class: "white-dragon-inner", x: 28, y: 34, width: 44, height: 62, rx: 5}),
    );
  } else {
    const className = spec.label === "發" ? "honor-green" : spec.label === "中" ? "honor-red" : "honor-wind";
    svg.append(svgNode(documentRef, "text", {class: `mahjong-glyph honor-glyph ${className}`, x: 50, y: 86, "text-anchor": "middle"}, spec.label));
  }
  return svg;
}
