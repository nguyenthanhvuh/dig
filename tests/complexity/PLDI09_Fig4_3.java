public class PLDI09_Fig4_3 {
    public static void vtrace1(int n, int m, int t){}
    public static void main (String[] args) {}
    public static int mainQ(int n, int m){
	assert (m > 0);
	assert (n > m);
	int i = 0;
	int j = 0;
	int t = 0;
	while(i<n){
	    if (j < m) {
		j++;
	    }else{
		j=0;
		i++;
	    }
	    t++;
	}
	vtrace1(n, m, t);
	//dig2: -m <= -1, m*n + n - t == 0, m - n <= -1

	return 0;
    }

}

