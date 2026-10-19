import java.math.BigDecimal;

public class OrderRecord {
    private OrderHeader orderHeader;
    private BigDecimal orderTotal;
    public OrderHeader getOrderHeader() { return orderHeader; }
    public void setOrderHeader(OrderHeader orderHeader) { this.orderHeader = orderHeader; }
    public BigDecimal getOrderTotal() { return orderTotal; }
    public void setOrderTotal(BigDecimal orderTotal) { this.orderTotal = orderTotal; }

    public static class OrderHeader {
        private int orderId;
        private OrderDate orderDate;
        public int getOrderId() { return orderId; }
        public void setOrderId(int orderId) { this.orderId = orderId; }
        public OrderDate getOrderDate() { return orderDate; }
        public void setOrderDate(OrderDate orderDate) { this.orderDate = orderDate; }

        public static class OrderDate {
            private short orderYear;
            private byte orderMonth;
            private byte orderDay;
            public short getOrderYear() { return orderYear; }
            public void setOrderYear(short orderYear) { this.orderYear = orderYear; }
            public byte getOrderMonth() { return orderMonth; }
            public void setOrderMonth(byte orderMonth) { this.orderMonth = orderMonth; }
            public byte getOrderDay() { return orderDay; }
            public void setOrderDay(byte orderDay) { this.orderDay = orderDay; }
        }
    }

    public static void validateOrderId(int v) {
        if (v < 0 || v > 99999999) {
            throw new IllegalArgumentException("ORDER-ID: " + v + " outside 0..99999999");
        }
    }

    public static void validateOrderYear(short v) {
        if (v < 0 || v > 9999) {
            throw new IllegalArgumentException("ORDER-YEAR: " + v + " outside 0..9999");
        }
    }

    public static void validateOrderMonth(byte v) {
        if (v < 0 || v > 99) {
            throw new IllegalArgumentException("ORDER-MONTH: " + v + " outside 0..99");
        }
    }

    public static void validateOrderDay(byte v) {
        if (v < 0 || v > 99) {
            throw new IllegalArgumentException("ORDER-DAY: " + v + " outside 0..99");
        }
    }
}
