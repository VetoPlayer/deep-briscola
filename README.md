# deep-briscola

Self play implementation branch



### Results obtained

* 70 000 epochs training using DQRN and self play

	* The agents is not so good at playing against past copies of himself. He wins 55% of matches against them which is not a bad result but it is not a good one either.
	* An other issue is that the variance of winning rate doesn't decline over time. We can see from the graph below that its time series is almost stationary

<img src="Training 70000 epochs/Graphics/last.png" align="middle" />



