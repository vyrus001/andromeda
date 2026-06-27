const providerDefaults = {
  grok: 'latest',
  openai: 'gpt-4.1-mini',
  claude: 'claude-sonnet-4-20250514',
  ollama: 'llama3.2',
};

const state = {
  nodes: [],
  links: [],
  selectedId: null,
  socket: null,
  testMode: false,
};

const svg = d3.select('#graph');
const root = svg.append('g').attr('class', 'graph-root');
const linkLayer = root.append('g').attr('class', 'links');
const nodeLayer = root.append('g').attr('class', 'nodes');

const simulation = d3.forceSimulation()
  .force('link', d3.forceLink().id((d) => d.id).distance((d) => d.type === 'IS_REACHABLE_BY' ? 150 : 120))
  .force('charge', d3.forceManyBody().strength(-520))
  .force('center', d3.forceCenter(0, 0))
  .force('collide', d3.forceCollide(70))
  .on('tick', ticked);

const zoom = d3.zoom()
  .scaleExtent([0.25, 2.8])
  .on('zoom', (event) => root.attr('transform', event.transform));

svg.call(zoom);

const socketDot = document.querySelector('#socketDot');
const socketText = document.querySelector('#socketText');
const fitGraph = document.querySelector('#fitGraph');
const nodePanel = document.querySelector('#nodePanel');
const chatOutput = document.querySelector('#chatOutput');
const chatForm = document.querySelector('#chatForm');
const provider = document.querySelector('#provider');
const model = document.querySelector('#model');
const message = document.querySelector('#message');

model.value = providerDefaults[provider.value];

provider.addEventListener('change', () => {
  model.value = providerDefaults[provider.value] || '';
});


fitGraph.addEventListener('click', () => fitToView());

chatForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const content = message.value.trim();
  if (!content) return;
  appendChat(`you: ${content}`);
  sendSocket({
    type: 'chat',
    payload: {
      provider: provider.value,
      model: model.value.trim() || undefined,
      message: content,
    },
  });
  message.value = '';
});

message.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  chatForm.requestSubmit();
});

window.addEventListener('resize', () => {
  resizeGraph();
  fitToView(false);
});

connect();
resizeGraph();

function connect() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
  state.socket = socket;

  socket.addEventListener('open', () => {
    setSocketStatus(true);
  });
  socket.addEventListener('close', () => {
    setSocketStatus(false);
    setTimeout(connect, 1200);
  });
  socket.addEventListener('message', (event) => {
    const payload = JSON.parse(event.data);
    handleSocketMessage(payload);
  });
}

function sendSocket(payload) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    appendChat('socket offline');
    return;
  }
  state.socket.send(JSON.stringify(payload));
}

function handleSocketMessage(payload) {
  if (payload.type === 'hello') {
    state.testMode = Boolean(payload.test_mode);
    return;
  }
  if (payload.type === 'graph_snapshot' || payload.type === 'graph_update') {
    updateGraph(payload.graph);
    return;
  }
  if (payload.type === 'chat_started') {
    appendChat(`${payload.provider}: thinking`);
    return;
  }
  if (payload.type === 'chat_response') {
    appendChat(`${payload.provider}: ${payload.message}`);
    return;
  }
  if (payload.type === 'chat_error') {
    appendChat(`error: ${payload.message}`);
  }
}

function setSocketStatus(online) {
  socketDot.classList.toggle('online', online);
  socketDot.classList.toggle('offline', !online);
  socketText.textContent = online ? 'online' : 'offline';
}


function appendChat(text) {
  chatOutput.textContent = text;
}

function updateGraph(graph) {
  const previousNodes = new Map(state.nodes.map((node) => [node.id, node]));
  state.nodes = graph.nodes.map((node) => {
    const previous = previousNodes.get(node.id);
    return previous ? Object.assign(previous, node) : node;
  });
  state.links = graph.links.map((link) => ({ ...link }));

  simulation.nodes(state.nodes);
  simulation.force('link').links(state.links);
  render();
  resizeGraph();
  simulation.alpha(0.8).restart();
  if (!state.selectedId && state.nodes.length) {
    scheduleDefaultFit();
  }
}

function render() {
  const links = linkLayer
    .selectAll('line')
    .data(state.links, (d) => d.id);

  links.exit().remove();

  links.enter()
    .append('line')
    .attr('class', (d) => `link ${d.type === 'IS_REACHABLE_BY' ? 'reach' : 'comm'}`)
    .append('title')
    .text((d) => `${d.source} ${d.label} ${d.target}`);

  links
    .attr('class', (d) => `link ${d.type === 'IS_REACHABLE_BY' ? 'reach' : 'comm'}`);

  const nodes = nodeLayer
    .selectAll('g.node')
    .data(state.nodes, (d) => d.id);

  nodes.exit().remove();

  const entered = nodes.enter()
    .append('g')
    .attr('class', (d) => `node ${d.status || 'unknown'}`)
    .call(drag(simulation))
    .on('click', (_event, d) => selectNode(d));

  entered.append('circle')
    .attr('class', 'node-shell')
    .attr('r', 33);

  entered.append('text')
    .attr('class', 'logo-fallback')
    .text((d) => d.os_code || 'OS');

  entered.append('image')
    .attr('class', 'os-logo')
    .attr('x', -24)
    .attr('y', -24)
    .attr('width', 48)
    .attr('height', 48)
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .on('error', function () {
      d3.select(this).style('display', 'none');
    });

  entered.append('text')
    .attr('class', 'arch-label')
    .attr('y', -42);

  entered.append('text')
    .attr('class', 'host-label')
    .attr('y', 50);

  entered.append('title');

  const merged = entered.merge(nodes);
  merged
    .attr('class', (d) => `node ${d.status || 'unknown'} ${state.selectedId === d.id ? 'selected' : ''}`);

  merged.select('image.os-logo')
    .style('display', null)
    .attr('href', (d) => d.logo_path);

  merged.select('text.logo-fallback').text((d) => d.os_code || 'OS');
  merged.select('text.arch-label').text((d) => d.arch || 'unknown');
  merged.select('text.host-label').text((d) => d.hostname || d.id);
  merged.select('title').text((d) => `${d.hostname}\n${d.os} ${d.arch}\n${d.last_seen || ''}`);
}

function ticked() {
  linkLayer.selectAll('line')
    .attr('x1', (d) => d.source.x)
    .attr('y1', (d) => d.source.y)
    .attr('x2', (d) => d.target.x)
    .attr('y2', (d) => d.target.y);

  nodeLayer.selectAll('g.node')
    .attr('transform', (d) => `translate(${d.x || 0},${d.y || 0})`);
}

function resizeGraph() {
  const rect = svg.node().getBoundingClientRect();
  svg.attr('viewBox', `${-rect.width / 2} ${-rect.height / 2} ${rect.width} ${rect.height}`);
  simulation.force('center', d3.forceCenter(0, 0));
}

function fitToView(animate = true) {
  if (!state.nodes.length) return;
  const bounds = root.node().getBBox();
  const full = svg.node().getBoundingClientRect();
  if (!bounds.width || !bounds.height || !full.width || !full.height) return;

  const padding = 110;
  const widthScale = (full.width - padding) / bounds.width;
  const heightScale = (full.height - padding) / bounds.height;
  const scale = Math.max(0.25, Math.min(1.55, Math.min(widthScale, heightScale)));
  const translate = [
    -scale * (bounds.x + bounds.width / 2),
    -scale * (bounds.y + bounds.height / 2),
  ];
  const transform = d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale);
  const target = animate ? svg.transition().duration(220) : svg;
  target.call(zoom.transform, transform);
}

function scheduleDefaultFit() {
  requestAnimationFrame(() => fitToView(false));
  setTimeout(() => fitToView(false), 180);
  setTimeout(() => fitToView(false), 520);
}

function selectNode(node) {
  state.selectedId = node.id;
  render();
  nodePanel.classList.add('visible');
  nodePanel.innerHTML = `
    <h2>${escapeHtml(node.hostname || node.id)}</h2>
    <dl>
      <dt>arch</dt><dd>${escapeHtml(node.arch || 'unknown')}</dd>
      <dt>os</dt><dd>${escapeHtml(node.os || 'unknown')}</dd>
      <dt>status</dt><dd>${escapeHtml(node.status || 'unknown')}</dd>
      <dt>ip</dt><dd>${escapeHtml((node.ip_addresses || []).join(', ') || 'none')}</dd>
      <dt>seen</dt><dd>${escapeHtml(node.last_seen || 'unknown')}</dd>
    </dl>
  `;
}

function drag(sim) {
  function dragstarted(event, d) {
    if (!event.active) sim.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }

  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }

  function dragended(event, d) {
    if (!event.active) sim.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }

  return d3.drag()
    .on('start', dragstarted)
    .on('drag', dragged)
    .on('end', dragended);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}
