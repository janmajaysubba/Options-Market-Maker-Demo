
import numpy as np

def binomial_price(S,K,T,r,sigma,N=400,option="call",style="amer",q=0.0):
    dt=T/N; u=np.exp(sigma*np.sqrt(dt)); d=1/u
    p=(np.exp((r-q)*dt)-d)/(u-d)
    if not (0<p<1): raise ValueError("bad params; adjust N or inputs")
    ST=np.array([S*(u**j)*(d**(N-j)) for j in range(N+1)])
    V=np.maximum(ST-K,0.0) if option=="call" else np.maximum(K-ST,0.0)
    disc=np.exp(-r*dt)
    for i in range(N-1,-1,-1):
        V=disc*(p*V[1:i+2]+(1-p)*V[0:i+1])
        if style=="amer":
            S_nodes=np.array([S*(u**j)*(d**(i-j)) for j in range(i+1)])
            exercise=np.maximum(S_nodes-K,0.0) if option=="call" else np.maximum(K-S_nodes,0.0)
            V=np.maximum(V,exercise)
    return float(V[0])
