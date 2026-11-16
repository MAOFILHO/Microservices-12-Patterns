import { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import ApiGatewayDemo from "../patterns/demos/ApiGatewayDemo";
import BoundedContextDemo from "../patterns/demos/BoundedContextDemo";
import CiCdDemo from "../patterns/demos/CiCdDemo";
import CircuitBreakerDemo from "../patterns/demos/CircuitBreakerDemo";
import ContainerizationDemo from "../patterns/demos/ContainerizationDemo";
import ContractTestingDemo from "../patterns/demos/ContractTestingDemo";
import EventDrivenDemo from "../patterns/demos/EventDrivenDemo";
import DatabasePerServiceDemo from "../patterns/demos/DatabasePerServiceDemo";
import ObservabilityDemo from "../patterns/demos/ObservabilityDemo";
import SagaDemo from "../patterns/demos/SagaDemo";
import ServiceDiscoveryDemo from "../patterns/demos/ServiceDiscoveryDemo";
import StatelessDemo from "../patterns/demos/StatelessDemo";
import { PATTERNS } from "../patterns/content";

const DEMOS: Record<string, () => ReactNode> = {
  "database-per-service": () => <DatabasePerServiceDemo />,
  "bounded-context": () => <BoundedContextDemo />,
  "api-gateway": () => <ApiGatewayDemo />,
  observability: () => <ObservabilityDemo />,
  "circuit-breaker": () => <CircuitBreakerDemo />,
  "stateless-services": () => <StatelessDemo />,
  "contract-testing": () => <ContractTestingDemo />,
  "service-discovery": () => <ServiceDiscoveryDemo />,
  "event-driven-architecture": () => <EventDrivenDemo />,
  saga: () => <SagaDemo />,
  containerization: () => <ContainerizationDemo />,
  "ci-cd-pipeline": () => <CiCdDemo />,
};

export default function PatternPage() {
  const { slug } = useParams();
  const pattern = PATTERNS.find((p) => p.slug === slug);

  if (!pattern || !pattern.live) {
    return (
      <section className="card">
        <h1>{pattern ? pattern.name : "Unknown pattern"}</h1>
        <p className="muted">{pattern ? `This demo arrives in ${pattern.milestone}.` : "No pattern with that name."}</p>
        <Link to="/patterns">Back to all patterns</Link>
      </section>
    );
  }

  return (
    <div className="grid" style={{ gap: "1.5rem" }}>
      <section className="card">
        <p className="muted" style={{ margin: 0 }}>
          <Link to="/patterns">Patterns</Link> / Pattern {pattern.n}
        </p>
        <h1>{pattern.name}</h1>
        <p>{pattern.what}</p>
        <h3>The problem it solves</h3>
        <p className="muted">{pattern.problem}</p>
      </section>

      <div className="grid cols-2">
        <section className="card">
          <h3>How this project does it</h3>
          <ul>
            {pattern.inThisProject?.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </section>
        <section className="card">
          <h3>When not to use it</h3>
          <ul>
            {pattern.whenNotToUse?.map((line) => <li key={line}>{line}</li>)}
          </ul>
          {pattern.source && (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              Source:{" "}
              <a href={pattern.source.url} target="_blank" rel="noreferrer">
                {pattern.source.label}
              </a>
            </p>
          )}
        </section>
      </div>

      <section className="card">
        <h2>Live demo</h2>
        {DEMOS[pattern.slug]?.()}
      </section>
    </div>
  );
}
