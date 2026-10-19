import java.math.BigDecimal;
import java.math.BigInteger;

public class FinancialRecord {
    private int recordId;
    private int transactionCount;
    private BigDecimal unitPrice;
    private long largeId;
    private BigInteger hugeValue;
    private float sensorReading;
    private double preciseReading;
    public int getRecordId() { return recordId; }
    public void setRecordId(int recordId) { this.recordId = recordId; }
    public int getTransactionCount() { return transactionCount; }
    public void setTransactionCount(int transactionCount) { this.transactionCount = transactionCount; }
    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) { this.unitPrice = unitPrice; }
    public long getLargeId() { return largeId; }
    public void setLargeId(long largeId) { this.largeId = largeId; }
    public BigInteger getHugeValue() { return hugeValue; }
    public void setHugeValue(BigInteger hugeValue) { this.hugeValue = hugeValue; }
    public float getSensorReading() { return sensorReading; }
    public void setSensorReading(float sensorReading) { this.sensorReading = sensorReading; }
    public double getPreciseReading() { return preciseReading; }
    public void setPreciseReading(double preciseReading) { this.preciseReading = preciseReading; }

    public static void validateRecordId(int v) {
        if (v < 0 || v > 99999) {
            throw new IllegalArgumentException("RECORD-ID: " + v + " outside 0..99999");
        }
    }

    public static void validateTransactionCount(int v) {
        if (v < -999999999 || v > 999999999) {
            throw new IllegalArgumentException("TRANSACTION-COUNT: " + v + " outside -999999999..999999999");
        }
    }

    public static void validateLargeId(long v) {
        if (v < -999999999999999999L || v > 999999999999999999L) {
            throw new IllegalArgumentException("LARGE-ID: " + v + " outside -999999999999999999..999999999999999999");
        }
    }
}
