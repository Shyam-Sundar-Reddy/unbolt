public class InventoryRecord {
    private short warehouseId;
    private byte itemCount;
    private ItemTable[] itemTable;
    public short getWarehouseId() { return warehouseId; }
    public void setWarehouseId(short warehouseId) { this.warehouseId = warehouseId; }
    public byte getItemCount() { return itemCount; }
    public void setItemCount(byte itemCount) { this.itemCount = itemCount; }
    public ItemTable[] getItemTable() { return itemTable; }
    public void setItemTable(ItemTable[] itemTable) { this.itemTable = itemTable; }

    public static class ItemTable {
        private String itemSku;
        private short itemQty;
        public String getItemSku() { return itemSku; }
        public void setItemSku(String itemSku) { this.itemSku = itemSku; }
        public short getItemQty() { return itemQty; }
        public void setItemQty(short itemQty) { this.itemQty = itemQty; }
    }

    public static void validateWarehouseId(short v) {
        if (v < 0 || v > 9999) {
            throw new IllegalArgumentException("WAREHOUSE-ID: " + v + " outside 0..9999");
        }
    }

    public static void validateItemCount(byte v) {
        if (v < 0 || v > 99) {
            throw new IllegalArgumentException("ITEM-COUNT: " + v + " outside 0..99");
        }
    }

    public static void validateItemQty(short v) {
        if (v < 0 || v > 9999) {
            throw new IllegalArgumentException("ITEM-QTY: " + v + " outside 0..9999");
        }
    }
}
