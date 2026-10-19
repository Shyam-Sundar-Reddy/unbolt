import java.math.BigDecimal;

public class CustomerRecord {
    private int customerId;
    private short customerAge;
    private BigDecimal accountBalance;
    public int getCustomerId() { return customerId; }
    public void setCustomerId(int customerId) { this.customerId = customerId; }
    public short getCustomerAge() { return customerAge; }
    public void setCustomerAge(short customerAge) { this.customerAge = customerAge; }
    public BigDecimal getAccountBalance() { return accountBalance; }
    public void setAccountBalance(BigDecimal accountBalance) { this.accountBalance = accountBalance; }

    public static void validateCustomerId(int v) {
        if (v < 0 || v > 999999) {
            throw new IllegalArgumentException("CUSTOMER-ID: " + v + " outside 0..999999");
        }
    }

    public static void validateCustomerAge(short v) {
        if (v < -999 || v > 999) {
            throw new IllegalArgumentException("CUSTOMER-AGE: " + v + " outside -999..999");
        }
    }
}
