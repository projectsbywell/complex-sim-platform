# Glossary — complex-sim-platform

**Glossário Técnico**

---

### A

**Adam Optimizer**
Algoritmo de otimização adaptativa que combina momentum e
taxa de aprendizado adaptativa. Calcula estimativas exponenciais
móveis dos gradientes primeira e segunda ordem.

**API Gateway**
Componente de roteamento que direciona requisições HTTP para
os handlers apropriados no backend. Implementa versionamento,
autenticação e rate limiting.

**Batch Processing**
Processamento de dados em blocos. Diferente de streaming,
processa coleções completas de registros de uma vez.

**Box2D-lite**
Motor de física 2D leve que usa o método de impulso sequencial
para resolução de contatos e colisões entre corpos rígidos.

**CORS (Cross-Origin Resource Sharing)**
Mecanismo de segurança que controla quais origens podem
acessar recursos de um servidor. Configurado via headers HTTP.

**Checksum**
Valor hash usado para verificar integridade de dados.
Comum para validar downloads e arquivos de modelo.

**CI/CD (Continuous Integration/Continuous Deployment)**
Prática de automação de testes, construção e implantação
de software. GitHub Actions ou GitLab CI são exemplos comuns.

---

### D

**Determinism**
Propriedade onde o mesmo input sempre produz o mesmo output.
Essencial para reprodutibilidade de simulações científicas.

**Diffusion**
Processo de propagação de propriedades (como densidade)
através de um meio. Na simulação de fluidos, controla
a dispersão de quantidades.

**Docker**
Plataforma de containerização que empacota aplicações com
suas dependências em imagens isoladas.

**Drift**
Desvio gradual de um sistema em relação ao seu comportamento
esperado. Em simulações numéricas, drift energético indica
erro de integração.

---

### E

**Euler Method**
Método de integração numérica de primeira ordem. Simples mas
impreciso para sistemas Hamiltonianos devido ao drift energético.

**Epoch**
Uma passagem completa do conjunto de dados de treinamento
através do modelo neural. Uma época = um ciclo de treinamento.

---

### F

**FastAPI**
Framework web moderno para Python com suporte nativo a async,
type hints automáticos e geração de documentação OpenAPI.

**Fluid Simulation**
Simulação computacional de líquidos usando equações de Navier-Stokes.
A plataforma usa o método Stable Fluids de Stam (1999).

**Force Field**
Campo de forças que influencia partículas em uma simulação.
Pode representar gravidade, vento, eletricidade, etc.

**Frequency**
Número de ciclos por unidade de tempo. Em séries temporais,
determina a periodicidade do sinal.

---

### G

**Gradient**
Derivada vetorial de uma função. Indica a direção e taxa de
maior aumento. Essencial para algoritmos de otimização como Adam.

**Gauss-Seidel**
Método iterativo para resolver sistemas de equações lineares.
Usado no solver de pressão da simulação de fluidos (Stable Fluids).

**Gzip**
Algoritmo de compressão sem perdas. Usado para reduzir tamanho
de arquivos de dados e checkpoints.

---

### H

**Hash**
Função que mapeia dados de tamanho arbitrário para saída de
tamanho fixo. Usado para integridade, autenticação e indexação.

**Hidden Layer**
Camada intermediária de uma rede neural entre a entrada e saída.
Determina a capacidade de representação do modelo.

**HTTP (Hypertext Transfer Protocol)**
Protocolo de comunicação para a web. REST APIs usam métodos
HTTP (GET, POST, PUT, DELETE).

---

### I

**Incompressibility**
Propriedade de fluides onde a densidade permanece constante.
Enforçada via equação de continuidade (divergência zero).

**IQR (Interquartile Range)**
Intervalo entre o primeiro e terceiro quartil. Usado para
detecção de outliers robusta.

**Iterative Method**
Algoritmo que aproxima soluções através de repetições sucessivas.
Usado no solver de pressão e na resolução de contatos.

---

### J

**JAX**
Framework do Google para computação diferenciável de alto desempenho.
Suporta JIT compilation e operações automáticas em GPU/TPU.

**JSON (JavaScript Object Notation)**
Formato de dados leve e legível por humanos. Usado para
configurações, APIs e checkpoints do modelo.

---

### K

**Kubernetes**
Sistema de orquestração de contêineres para automação de
deploy, escalamento e gerenciamento de aplicações containerizadas.

**Kermack-McKendrick**
Modelo matemático epidemiológico SIR (Susceptible-Infected-Recovered).
Fundacional em epidemiologia matemática.

---

### L

**Lagrangian**
Perspectiva que rastreia partículas individuais ao invés de
observar o campo em pontos fixos (Euleriano). O método semi-Lagrangiano
de Stam rastreia partículas para trás no tempo.

**LRU Cache (Least Recently Used)**
Estratégia de cache que remove o item menos recentemente
acessado quando o cache atinge sua capacidade máxima.

**Lotka-Volterra**
Sistema de equações diferenciais que modela interações
predador-presas. Produz órbitas periódicas no espaço de fases.

---

### M

**MLP (Multi-Layer Perceptron)**
Rede neural feed-forward com camadas totalmente conectadas.
Usada para aprendizado supervisionado de padrões em dados.

**Mass Conservation**
Princípio físico onde a massa total de um sistema permanece
constante. Enforçada via projeção de incompressibilidade.

**Middleware**
Componente de software que processa requisições antes de
chegar ao handler principal. Exemplos: autenticação, logging,
rate limiting.

**Model Checkpoint**
Snapshot do estado treinado de um modelo neural. Permite
retomar treinamento ou realizar inferência sem retreinar.

---

### N

**Navier-Stokes**
Equações fundamentais que descrevem o movimento de fluidos
viscosos. Combinam conservação de massa, momento e energia.

**NumPy**
Biblioteca fundamental de Python para computação numérica.
Fornece arrays multidimensionais e funções matemáticas otimizadas.

**Numba**
Compilador JIT para Python que acelera funções numéricas
transformando código Python em código máquina otimizado.

---

### O

**ODE (Ordinary Differential Equation)**
Equação diferencial envolvendo funções de uma única variável.
Usada em modelos SIR, Lotka-Volterra e integradores de partículas.

**Optimizer**
Algoritmo que atualiza os parâmetros de um modelo para
minimizar a função de perda. Adam é o otimizador padrão.

**Orchestration**
Coordenação automatizada de múltiplos serviços ou contêineres.
Kubernetes é o padrão da indústria para orquestração.

**Outlier**
Observação que se desvia significativamente do padrão dos
dados. Detectado via z-score ou método IQR.

---

### P

**Parquet**
Formato de armazenamento columnar otimizado para datasets
grandes. Usado para saídas de pipeline batch.

**Particle System**
Coleção de pontos discretos que simulam comportamento de
materiais contínuos. Cada partícula tem posição, velocidade, massa.

**Poisson Equation**
Equação diferencial parcial usada para resolver pressão em
fluidos incompressíveis. O solver de Stam usa Gauss-Seidel.

**Pipeline**
Sequência de etapas de processamento de dados. Dois tipos:
batch (processamento em lote) e streaming (tempo real).

**Port Binding**
Exposição de um serviço em uma porta específica do host.
O backend expõe a porta 8000 por padrão.

**Property-Based Testing**
Abordagem de teste onde propriedades invariants são verificadas
para entradas geradas automaticamente (ex: Hypothesis).

---

### Q

**Quality Score**
Métrica 0-100 que avalia a qualidade dos dados com base em
taxa de dados faltantes, detecção de outliers e validação de schema.

**Query**
Operação de recuperação de dados de um banco de dados ou
sistema de armazenamento.

---

### R

**Rate Limiting**
Controle da taxa de requisições permitidas por cliente.
Previne abuso e protege recursos do servidor.

**Repository**
Local de armazenamento de código-fonte com controle de versão.
Git é o sistema de controle de versão padrão.

**Reproducibility**
Capacidade de reproduzir resultados experimentais usando
os mesmos dados, código e sementes aleatórias.

**Rest API**
Arquitetura de serviço web baseada em métodos HTTP e recursos
identificados por URLs. Stateless e escalável.

**R² Score**
Coeficiente de determinação que mede a proporção da variância
explicada por um modelo de regressão. Varia de 0 a 1.

---

### S

**Schema**
Definição estrutural de dados que especifica campos, tipos e
restrições. Usado para validação automática de entradas.

**Semi-Lagrangian**
Método numérico para equações de advecção que rastreia
características para trás no tempo, garantindo estabilidade
incondicional. Base do Stable Fluids de Stam.

**SIGGRAPH**
Conferência anual de computação gráfica. Onde Stam publicou
Stable Fluids em 1999.

**Softmax**
Função de ativação que converte valores reais em probabilidades
que somam 1. Usada para classificação multi-classe.

**Stable Fluids**
Método de simulação de fluidos de Jos Stam (1999) usando
semi-Lagrangian advection com solver de pressão implícito.

**Stream Processing**
Processamento contínuo de dados em tempo real. Diferente de
batch processing, processa cada registro conforme chega.

**Symplectic Integrator**
Integrador numérico que preserva a estrutura geométrica do
espaço de fase. O Verlet é o protótipo para sistemas Hamiltonianos.

---

### T

**TLS (Transport Layer Security)**
Protocolo criptográfico que fornece comunicação segura na
internet. Versão 1.3 é o padrão atual.

**Token Bucket**
Algoritmo de rate limiting que permite rajadas de requisições
até um tamanho máximo, enquanto o bucket se reposiciona
a uma taxa constante.

**Throughput**
Quantidade de dados processados por unidade de tempo.
Medido em registros/segundo ou MB/s.

**Time Step**
Intervalo de tempo entre cada iteração de uma simulação
numérica. Determina precisão e estabilidade.

**Type Hint**
Anotação em Python que especifica o tipo esperado de uma
variável ou retorno de função. Melhora legibilidade e tooling.

---

### V

**Verlet Integration**
Método de integração numérica simétrico e simplectico.
Preserva energia em sistemas Hamiltonianos a longo prazo.
Usado para dinâmica de partículas na plataforma.

**Velocity Verlet**
Variante do método Verlet que atualiza posição e velocidade
simultaneamente. Segunda ordem de precisão O(dt²).

**WebSocket**
Protocolo de comunicação full-duplex sobre uma única conexão
TCP. Essencial para streaming de estado em tempo real.

---

### Z

**Z-Score**
Medida de quantos desvios-padrão um dado está da média.
Usado para detecção de outliers (|z| > 3 é considerado outlier).
